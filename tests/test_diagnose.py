from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from pdf_size_fit.diagnose import Route, diagnose_pdf
from tools.generate_fixtures import generate_image_heavy, generate_small, generate_vector


def test_skip_below_target(tmp_path: Path) -> None:
    path = tmp_path / "small.pdf"
    generate_small(path)
    result = diagnose_pdf(path, target_bytes=100_000)
    assert result.route is Route.SKIP


def test_image_heavy_route(tmp_path: Path) -> None:
    path = tmp_path / "image.pdf"
    generate_image_heavy(path, pages=1, image_size=700)
    result = diagnose_pdf(path, target_bytes=50_000)
    assert result.route is Route.IMAGE_HEAVY
    assert result.image_ratio >= 0.60


def test_monochrome_vector_route(tmp_path: Path) -> None:
    path = tmp_path / "mono.pdf"
    generate_vector(path, color=False, pages=1, repeats=3000)
    result = diagnose_pdf(path, target_bytes=20_000, vector_heavy_ratio=0.25)
    assert result.route is Route.VECTOR_MONOCHROME
    assert result.rendered_color_fraction is not None
    assert result.rendered_color_fraction < 0.01


def test_color_vector_route(tmp_path: Path) -> None:
    path = tmp_path / "color.pdf"
    generate_vector(path, color=True, pages=1, repeats=3000)
    result = diagnose_pdf(path, target_bytes=20_000, vector_heavy_ratio=0.25)
    assert result.route is Route.VECTOR_COLOR
    assert result.rendered_color_fraction is not None
    assert result.rendered_color_fraction >= 0.01


def test_color_on_middle_page_is_not_misclassified_as_monochrome(tmp_path: Path) -> None:
    mono = tmp_path / "mono4.pdf"
    color = tmp_path / "color1.pdf"
    mixed = tmp_path / "mixed.pdf"
    generate_vector(mono, color=False, pages=4, repeats=2500)
    generate_vector(color, color=True, pages=1, repeats=2500)

    mono_reader = PdfReader(str(mono))
    color_reader = PdfReader(str(color))
    writer = PdfWriter()
    writer.add_page(mono_reader.pages[0])
    writer.add_page(mono_reader.pages[1])
    writer.add_page(color_reader.pages[0])
    writer.add_page(mono_reader.pages[2])
    writer.add_page(mono_reader.pages[3])
    with mixed.open("wb") as fh:
        writer.write(fh)

    result = diagnose_pdf(mixed, target_bytes=20_000, vector_heavy_ratio=0.20)
    assert result.route is Route.VECTOR_COLOR
    assert result.rendered_color_fraction is not None
    assert result.rendered_color_fraction >= 0.01


def test_unclassified_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "small-but-over-tiny-target.pdf"
    generate_small(path)
    result = diagnose_pdf(path, target_bytes=1)
    assert result.route is Route.UNCLASSIFIED


@pytest.mark.parametrize("target", [0, -1])
def test_invalid_target_rejected(tmp_path: Path, target: int) -> None:
    path = tmp_path / "small.pdf"
    generate_small(path)
    with pytest.raises(ValueError, match="target_bytes"):
        diagnose_pdf(path, target_bytes=target)
