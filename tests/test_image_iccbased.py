"""Synthetic ICCBased RGB regression and fail-closed tests for Stage 2 (#42)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from PIL import Image, ImageCms, ImageChops, ImageStat
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    NameObject,
    NumberObject,
)
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from pdf_size_fit.image_fit import (
    ImageFitStatus,
    UnsupportedImageError,
    _build_candidate,
    fit_image_heavy_pdf,
)
from pdf_size_fit.image_first_fit import fit_image_heavy_pdf_first_fit
from tools.generate_fixtures import generate_image_heavy


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _srgb_profile() -> bytes:
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def _gradient_shared_pdf(path: Path) -> None:
    # Smooth, nontrivial color variation provides a meaningful JPEG fidelity
    # assertion. Pure random noise is inappropriate for a strict pixel metric.
    image = Image.new("RGB", (300, 300))
    pixels = image.load()
    for y in range(300):
        for x in range(300):
            pixels[x, y] = (
                round(x * 255 / 299),
                round(y * 255 / 299),
                round((x + y) * 255 / 598),
            )
    c = canvas.Canvas(str(path), pagesize=A4)
    reader = ImageReader(image)
    for _ in range(2):
        c.drawImage(reader, 0, 0, width=A4[0], height=A4[1])
        c.showPage()
    c.save()


def _make_icc_pdf(
    source: Path,
    target: Path,
    *,
    n: int = 3,
    alternate: str = "/DeviceRGB",
    profile_data: bytes | None = None,
    range_values: list[int] | None = None,
    icc_extra_key: bool = False,
    base_decode: bool = False,
    bits_per_component: int | None = None,
) -> bytes:
    profile_bytes = _srgb_profile() if profile_data is None else profile_data
    writer = PdfWriter(clone_from=str(source))
    first = writer.pages[0].images[0]
    ref = first.indirect_reference
    assert ref is not None
    image_obj = ref.get_object()
    profile = DecodedStreamObject()
    profile.set_data(profile_bytes)
    profile[NameObject("/N")] = NumberObject(n)
    profile[NameObject("/Alternate")] = NameObject(alternate)
    if range_values is not None:
        profile[NameObject("/Range")] = ArrayObject(
            [NumberObject(value) for value in range_values]
        )
    if icc_extra_key:
        profile[NameObject("/Unexpected")] = NumberObject(1)
    profile_ref = writer._add_object(profile)
    image_obj[NameObject("/ColorSpace")] = ArrayObject(
        [NameObject("/ICCBased"), profile_ref]
    )
    if base_decode:
        image_obj[NameObject("/Decode")] = ArrayObject(
            [NumberObject(0), NumberObject(1)] * 3
        )
    if bits_per_component is not None:
        image_obj[NameObject("/BitsPerComponent")] = NumberObject(bits_per_component)
    with target.open("wb") as f:
        writer.write(f)
    return profile_bytes


def _icc_obj(reader: PdfReader):
    image = reader.pages[0].images[0]
    ref = image.indirect_reference
    assert ref is not None
    obj = ref.get_object()
    space = obj["/ColorSpace"]
    assert space[0] == "/ICCBased"
    return image, obj, space[1].get_object()


def test_iccbased_full_resolution_preserves_profile_shared_ref_and_pixels(
    tmp_path: Path,
) -> None:
    base = tmp_path / "base.pdf"
    source = tmp_path / "icc.pdf"
    output = tmp_path / "replaced.pdf"
    _gradient_shared_pdf(base)
    profile_bytes = _make_icc_pdf(base, source)
    source_hash = _sha256(source)

    original = PdfReader(str(source))
    assert len(original.pages) == 2
    original_image, original_obj, _ = _icc_obj(original)
    assert original_image.image.mode == "RGB"
    assert original.pages[0].images[0].indirect_reference.idnum == (
        original.pages[1].images[0].indirect_reference.idnum
    )

    count = _build_candidate(source, output, quality=95, scale=1.0)
    assert count == 1
    assert _sha256(source) == source_hash
    result = PdfReader(str(output))
    out_image, out_obj, out_profile = _icc_obj(result)
    assert len(result.pages) == 2
    assert result.pages[0].images[0].indirect_reference.idnum == (
        result.pages[1].images[0].indirect_reference.idnum
    )
    assert out_profile.get_data() == profile_bytes
    assert out_profile["/N"] == 3
    assert out_obj["/BitsPerComponent"] == 8
    assert out_image.image.mode == "RGB"
    assert original_obj["/Width"] == out_obj["/Width"]
    assert original_obj["/Height"] == out_obj["/Height"]
    # JPEG is lossy; quantify a synthetic pixel-difference bound, not equality.
    diff = ImageChops.difference(original_image.image, out_image.image)
    assert max(ImageStat.Stat(diff).mean) < 15


@pytest.mark.parametrize(
    "kwargs,reason",
    [
        ({"n": 4}, "only ICCBased /N 3"),
        ({"alternate": "/DeviceCMYK"}, "only ICCBased /N 3"),
        ({"range_values": [1, 0, 0, 1, 0, 1]}, "non-default ICCBased /Range"),
        ({"range_values": [0, 1, 0, 1]}, "unsupported ICCBased /Range"),
        ({"profile_data": b"not an ICC profile"}, "invalid or unreadable ICCBased"),
        ({"icc_extra_key": True}, "unsupported ICC profile dictionary keys"),
        ({"base_decode": True}, "unsupported image dictionary keys"),
        ({"bits_per_component": 16}, "unsupported bits per component"),
    ],
)
def test_iccbased_bad_semantics_fail_closed_without_writing(
    tmp_path: Path, kwargs: dict, reason: str
) -> None:
    base = tmp_path / "base.pdf"
    source = tmp_path / "unsupported.pdf"
    output = tmp_path / "must-not-exist.pdf"
    generate_image_heavy(base, pages=1, image_size=160)
    _make_icc_pdf(base, source, **kwargs)
    source_hash = _sha256(source)

    with pytest.raises(UnsupportedImageError, match=reason):
        _build_candidate(source, output, quality=70, scale=1.0)
    assert not output.exists()
    assert source_hash == _sha256(source)


@pytest.mark.parametrize("first_fit", [True, False])
def test_iccbased_integrates_with_both_image_fit_searches(
    tmp_path: Path, first_fit: bool
) -> None:
    base = tmp_path / "base.pdf"
    source = tmp_path / "icc.pdf"
    output = tmp_path / "fitted.pdf"
    generate_image_heavy(base, pages=1, image_size=300)
    profile_bytes = _make_icc_pdf(base, source)
    source_hash = _sha256(source)

    fn = fit_image_heavy_pdf_first_fit if first_fit else fit_image_heavy_pdf
    result = fn(source, output, target_bytes=120_000, min_quality=70)
    assert result.status is ImageFitStatus.FITTED
    assert result.output_size_bytes is not None
    assert result.output_size_bytes <= 120_000
    assert result.images_replaced == 1
    assert _sha256(source) == source_hash
    _, _, profile = _icc_obj(PdfReader(str(output)))
    assert profile.get_data() == profile_bytes


def _transparent_source(path: Path) -> None:
    image = Image.new("RGBA", (180, 180))
    pixels = image.load()
    for y in range(180):
        for x in range(180):
            pixels[x, y] = (x % 255, y % 255, (x + y) % 255, 60 + (x % 190))
    c = canvas.Canvas(str(path), pagesize=A4)
    c.drawImage(ImageReader(image), 0, 0, width=A4[0], height=A4[1], mask="auto")
    c.save()


def test_iccbased_full_resolution_preserves_nonopaque_soft_mask(tmp_path: Path) -> None:
    base = tmp_path / "base.pdf"
    source = tmp_path / "icc-smask.pdf"
    output = tmp_path / "fit.pdf"
    _transparent_source(base)
    _make_icc_pdf(base, source)
    source_reader = PdfReader(str(source))
    obj = source_reader.pages[0].images[0].indirect_reference.get_object()
    old_mask = obj["/SMask"].get_object().get_data()

    assert _build_candidate(source, output, quality=85, scale=1.0) == 1
    _, fitted_obj, profile = _icc_obj(PdfReader(str(output)))
    assert fitted_obj["/SMask"].get_object().get_data() == old_mask
    assert profile.get_data() == _srgb_profile()

    with pytest.raises(UnsupportedImageError, match="non-redundant or unproven /SMask"):
        _build_candidate(source, tmp_path / "no-scaled.pdf", quality=85, scale=0.80)
    assert not (tmp_path / "no-scaled.pdf").exists()


def test_iccbased_target_not_met_keeps_output_absent(tmp_path: Path) -> None:
    base = tmp_path / "base.pdf"
    source = tmp_path / "icc.pdf"
    output = tmp_path / "no-output.pdf"
    generate_image_heavy(base, pages=1, image_size=160)
    _make_icc_pdf(base, source)
    result = fit_image_heavy_pdf_first_fit(
        source, output, target_bytes=500, min_quality=70, min_scale=1.0
    )
    assert result.status is ImageFitStatus.TARGET_NOT_MET
    assert not output.exists()
