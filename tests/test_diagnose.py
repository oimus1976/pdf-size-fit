from pathlib import Path

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
