from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from pdf_size_fit.image_fit import ImageFitStatus, _build_candidate, fit_image_heavy_pdf
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
