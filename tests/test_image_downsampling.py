from __future__ import annotations

import hashlib
from pathlib import Path
import zlib

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from pdf_size_fit.image_fit import (
    ImageFitStatus,
    _build_candidate,
    _find_redundant_opaque_smask_images,
    fit_image_heavy_pdf,
)
from tools.generate_fixtures import generate_image_heavy


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _generate_transparent_image_pdf(path: Path, size: int = 300) -> None:
    image = Image.new("RGBA", (size, size))
    pixels = image.load()
    for y in range(size):
        for x in range(size):
            z = (x * 2654435761 + y * 2246822519) & 0xFFFFFFFF
            pixels[x, y] = (
                (z >> 16) & 255,
                (z >> 8) & 255,
                z & 255,
                80 + ((x + y) % 176),
            )

    c = canvas.Canvas(str(path), pagesize=A4, pageCompression=1)
    c.drawImage(ImageReader(image), 0, 0, width=A4[0], height=A4[1], mask="auto")
    c.save()


def _rewrite_first_soft_mask(
    source: Path,
    output: Path,
    *,
    non_opaque_first_sample: bool = False,
) -> None:
    writer = PdfWriter(clone_from=str(source))
    image = writer.pages[0].images[0]
    ref = image.indirect_reference
    assert ref is not None

    image_obj = ref.get_object()
    smask = image_obj.get("/SMask")
    assert smask is not None
    smask_obj = smask.get_object()

    width = int(smask_obj.get("/Width"))
    height = int(smask_obj.get("/Height"))
    data = bytearray(b"\xff" * (width * height))
    if non_opaque_first_sample:
        data[0] = 254

    # Synthetic-fixture mutation only: ReportLab may emit an ASCII85+Flate
    # filter chain. Normalize this test stream to a single FlateDecode filter
    # before replacing the encoded bytes, so the fixture does not depend on
    # ReportLab's chosen transport encoding.
    smask_obj[NameObject("/Filter")] = NameObject("/FlateDecode")
    smask_obj.pop(NameObject("/DecodeParms"), None)
    smask_obj._data = zlib.compress(bytes(data))

    with output.open("wb") as fh:
        writer.write(fh)


def _clone_with_leading_unreachable_object(source: Path, output: Path) -> None:
    reader = PdfReader(str(source))
    writer = PdfWriter()

    # Synthetic-fixture construction only: register an unreachable object
    # before cloning the page graph so clone_from drops it and renumbers the
    # reachable image objects.
    writer._add_object(DictionaryObject())
    writer.append_pages_from_reader(reader)

    with output.open("wb") as fh:
        writer.write(fh)


def test_target_not_met_is_explicit_when_downsampling_is_disabled(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "should-not-exist.pdf"
    generate_image_heavy(source, pages=1, image_size=300)

    result = fit_image_heavy_pdf(
        source,
        output,
        target_bytes=1_000,
        min_quality=70,
        min_scale=1.0,
    )

    assert result.status is ImageFitStatus.TARGET_NOT_MET
    assert result.selected_scale is None
    assert result.selected_quality is None
    assert result.attempts
    assert all(attempt.scale == 1.0 for attempt in result.attempts)
    assert not output.exists()


def test_downsampling_runs_only_after_full_resolution_quality_search_fails(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "output.pdf"
    full_min_quality = tmp_path / "full-q70.pdf"
    scaled_min_quality = tmp_path / "scaled-q70.pdf"
    generate_image_heavy(source, pages=1, image_size=300)
    before_hash = _sha256(source)

    _build_candidate(source, full_min_quality, quality=70, scale=1.0)
    _build_candidate(source, scaled_min_quality, quality=70, scale=0.90)
    full_size = full_min_quality.stat().st_size
    scaled_size = scaled_min_quality.stat().st_size
    assert scaled_size < full_size
    target = (full_size + scaled_size) // 2

    result = fit_image_heavy_pdf(
        source,
        output,
        target_bytes=target,
        min_quality=70,
        min_scale=0.50,
    )

    assert result.status is ImageFitStatus.FITTED
    assert result.selected_scale is not None
    assert 0.90 <= result.selected_scale < 1.0
    assert result.selected_quality is not None and result.selected_quality >= 70
    assert result.output_size_bytes is not None and result.output_size_bytes <= target
    assert any(attempt.scale < 1.0 for attempt in result.attempts)
    first_downsample_index = next(i for i, attempt in enumerate(result.attempts) if attempt.scale < 1.0)
    assert all(attempt.scale == 1.0 for attempt in result.attempts[:first_downsample_index])
    assert output.exists()
    assert _sha256(source) == before_hash


def test_downsampling_fails_closed_for_soft_mask_images(tmp_path: Path) -> None:
    source = tmp_path / "transparent.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_transparent_image_pdf(source)

    result = fit_image_heavy_pdf(
        source,
        output,
        target_bytes=1_000,
        min_quality=70,
        min_scale=0.50,
    )

    assert result.status is ImageFitStatus.UNSUPPORTED_IMAGE
    assert any("SMask" in reason for reason in result.reasons)
    assert not output.exists()


def test_downsampling_allows_proven_fully_opaque_soft_mask(tmp_path: Path) -> None:
    transparent = tmp_path / "transparent.pdf"
    source = tmp_path / "opaque-smask.pdf"
    output = tmp_path / "output.pdf"
    full_min_quality = tmp_path / "full-q70.pdf"
    scaled_min_quality = tmp_path / "scaled-q70.pdf"
    _generate_transparent_image_pdf(transparent)
    _rewrite_first_soft_mask(transparent, source)

    removable = _find_redundant_opaque_smask_images(source)
    assert removable

    _build_candidate(source, full_min_quality, quality=70, scale=1.0)
    _build_candidate(
        source,
        scaled_min_quality,
        quality=70,
        scale=0.90,
        removable_opaque_smask_refs=removable,
    )
    full_size = full_min_quality.stat().st_size
    scaled_size = scaled_min_quality.stat().st_size
    assert scaled_size < full_size
    target = (full_size + scaled_size) // 2

    result = fit_image_heavy_pdf(
        source,
        output,
        target_bytes=target,
        min_quality=70,
        min_scale=0.50,
    )

    assert result.status is ImageFitStatus.FITTED
    assert result.selected_scale is not None and result.selected_scale < 1.0
    assert output.exists()
    assert any("fully opaque /SMask" in reason for reason in result.reasons)

    output_reader = PdfReader(str(output))
    output_image = output_reader.pages[0].images[0]
    output_ref = output_image.indirect_reference
    assert output_ref is not None
    assert output_ref.get_object().get("/SMask") is None


def test_downsampling_allows_opaque_smask_after_writer_renumbers_image_ref(tmp_path: Path) -> None:
    transparent = tmp_path / "transparent.pdf"
    opaque_smask = tmp_path / "opaque-smask.pdf"
    source = tmp_path / "renumbered-source.pdf"
    output = tmp_path / "output.pdf"
    _generate_transparent_image_pdf(transparent)
    _rewrite_first_soft_mask(transparent, opaque_smask)
    _clone_with_leading_unreachable_object(opaque_smask, source)

    source_reader = PdfReader(str(source))
    source_ref = source_reader.pages[0].images[0].indirect_reference
    assert source_ref is not None
    source_key = (source_ref.idnum, source_ref.generation)

    removable = _find_redundant_opaque_smask_images(source)
    assert source_key in removable

    writer = PdfWriter(clone_from=str(source))
    writer_ref = writer.pages[0].images[0].indirect_reference
    assert writer_ref is not None
    writer_key = (writer_ref.idnum, writer_ref.generation)
    assert writer_key != source_key
    assert writer_key not in removable

    _build_candidate(
        source,
        output,
        quality=70,
        scale=0.90,
        removable_opaque_smask_refs=removable,
    )

    output_reader = PdfReader(str(output))
    output_ref = output_reader.pages[0].images[0].indirect_reference
    assert output_ref is not None
    assert output_ref.get_object().get("/SMask") is None


def test_downsampling_rejects_soft_mask_with_one_nonopaque_sample(tmp_path: Path) -> None:
    transparent = tmp_path / "transparent.pdf"
    source = tmp_path / "one-nonopaque-sample.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_transparent_image_pdf(transparent)
    _rewrite_first_soft_mask(transparent, source, non_opaque_first_sample=True)

    result = fit_image_heavy_pdf(
        source,
        output,
        target_bytes=1_000,
        min_quality=70,
        min_scale=0.50,
    )

    assert result.status is ImageFitStatus.UNSUPPORTED_IMAGE
    assert any("non-redundant or unproven /SMask" in reason for reason in result.reasons)
    assert not output.exists()


def test_target_not_met_remains_fail_closed_at_minimum_scale(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "should-not-exist.pdf"
    generate_image_heavy(source, pages=1, image_size=300)

    result = fit_image_heavy_pdf(
        source,
        output,
        target_bytes=1_000,
        min_quality=70,
        min_scale=0.50,
    )

    assert result.status is ImageFitStatus.TARGET_NOT_MET
    assert result.selected_scale is None
    assert any(attempt.scale < 1.0 for attempt in result.attempts)
    assert not output.exists()


def test_subpercent_minimum_scale_is_not_rounded_below_the_floor(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "should-not-exist.pdf"
    generate_image_heavy(source, pages=1, image_size=300)

    result = fit_image_heavy_pdf(
        source,
        output,
        target_bytes=1_000,
        min_quality=70,
        min_scale=0.999,
    )

    assert result.status is ImageFitStatus.TARGET_NOT_MET
    assert all(attempt.scale == 1.0 for attempt in result.attempts)
    assert not output.exists()


def test_min_scale_validation(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "output.pdf"
    generate_image_heavy(source, pages=1, image_size=100)

    with pytest.raises(ValueError, match="min_scale"):
        fit_image_heavy_pdf(source, output, min_scale=0.0)
    with pytest.raises(ValueError, match="min_scale"):
        fit_image_heavy_pdf(source, output, min_scale=1.01)
