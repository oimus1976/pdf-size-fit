from __future__ import annotations

from math import ceil
from pathlib import Path

from pypdf import PdfReader

from pdf_size_fit.image_fit import ImageFitStatus, _build_candidate, fit_image_heavy_pdf
from tools.generate_fixtures import generate_image_heavy


def test_downsampling_is_disabled_by_default(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "should-not-exist.pdf"
    generate_image_heavy(source, pages=1, image_size=300)

    result = fit_image_heavy_pdf(
        source,
        output,
        target_bytes=1_000,
        min_quality=100,
    )

    assert result.status is ImageFitStatus.TARGET_NOT_MET
    assert result.selected_scale is None
    assert result.attempts
    assert all(attempt.scale == 1.0 for attempt in result.attempts)
    assert not output.exists()


def test_downsampling_pixel_dimensions_do_not_fall_below_scale_floor(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "scaled.pdf"
    scale = 0.75
    generate_image_heavy(source, pages=1, image_size=5)

    source_image = PdfReader(str(source)).pages[0].images[0].image
    assert source_image is not None

    _build_candidate(source, output, quality=100, scale=scale)

    output_image = PdfReader(str(output)).pages[0].images[0].image
    assert output_image is not None
    expected_width = max(1, ceil(source_image.width * scale))
    expected_height = max(1, ceil(source_image.height * scale))
    assert output_image.size == (expected_width, expected_height)
    assert output_image.width / source_image.width >= scale
    assert output_image.height / source_image.height >= scale


def test_downsampling_selects_largest_fitting_integer_percent_scale(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "output.pdf"
    generate_image_heavy(source, pages=1, image_size=300)

    full = tmp_path / "full-q100.pdf"
    _build_candidate(source, full, quality=100, scale=1.0)
    full_size = full.stat().st_size

    candidate_sizes: dict[int, int] = {}
    for percent in range(99, 89, -1):
        candidate = tmp_path / f"scale-{percent}.pdf"
        _build_candidate(source, candidate, quality=100, scale=percent / 100.0)
        candidate_sizes[percent] = candidate.stat().st_size

    target = min(candidate_sizes.values())
    assert full_size > target
    expected_percent = max(
        percent for percent, size in candidate_sizes.items() if size <= target
    )

    result = fit_image_heavy_pdf(
        source,
        output,
        target_bytes=target,
        min_quality=100,
        min_scale=0.90,
    )

    assert result.status is ImageFitStatus.FITTED
    assert result.selected_scale == expected_percent / 100.0
    assert result.selected_quality == 100
    assert result.output_size_bytes is not None and result.output_size_bytes <= target
    assert output.exists()
