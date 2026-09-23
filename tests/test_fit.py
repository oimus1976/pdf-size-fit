from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pytest

from pdf_size_fit.diagnose import Diagnosis, Route
from pdf_size_fit.fit import FitResult, FitStatus, fit_pdf
from pdf_size_fit.fit_cli import main
from pdf_size_fit.image_fit import ImageFitResult, ImageFitStatus
from pdf_size_fit.color_fit import ColorFitResult, ColorFitStatus, FIXED_COLOR_DPI
from pdf_size_fit.monochrome_fit import MonochromeFitResult, MonochromeFitStatus


def _diagnosis(path: Path, route: Route, *, target_bytes: int = 10_000) -> Diagnosis:
    return Diagnosis(
        path=str(path),
        file_size_bytes=20_000,
        target_bytes=target_bytes,
        page_count=1,
        image_stream_bytes=15_000 if route is Route.IMAGE_HEAVY else 0,
        vector_stream_bytes=15_000 if route is Route.VECTOR_MONOCHROME else 0,
        image_ratio=0.75 if route is Route.IMAGE_HEAVY else 0.0,
        vector_ratio=0.75 if route is Route.VECTOR_MONOCHROME else 0.0,
        rendered_color_fraction=None,
        route=route,
        reasons=(f"diagnosed {route.value}",),
    )


def _image_result(
    input_path: Path,
    output_path: Path,
    status: ImageFitStatus = ImageFitStatus.FITTED,
) -> ImageFitResult:
    fitted = status is ImageFitStatus.FITTED
    return ImageFitResult(
        status=status,
        input_path=str(input_path),
        output_path=str(output_path) if fitted else None,
        input_size_bytes=20_000,
        output_size_bytes=9_000 if fitted else None,
        target_bytes=10_000,
        selected_quality=90 if fitted else None,
        images_replaced=1 if fitted else 0,
        attempts=(),
        reasons=(f"image route returned {status.value}",),
        selected_scale=1.0 if fitted else None,
    )


def _monochrome_result(
    input_path: Path,
    output_path: Path,
    status: MonochromeFitStatus = MonochromeFitStatus.FITTED,
) -> MonochromeFitResult:
    fitted = status is MonochromeFitStatus.FITTED
    return MonochromeFitResult(
        status=status,
        input_path=str(input_path),
        output_path=str(output_path) if fitted else None,
        input_size_bytes=20_000,
        output_size_bytes=8_000 if fitted else None,
        target_bytes=10_000,
        route=Route.VECTOR_MONOCHROME.value,
        dpi=300,
        bits_per_pixel=1,
        compression="CCITT Group 4",
        page_count=1,
        reasons=(f"monochrome route returned {status.value}",),
    )


def _color_result(
    input_path: Path,
    output_path: Path,
    status: ColorFitStatus = ColorFitStatus.FITTED,
) -> ColorFitResult:
    fitted = status is ColorFitStatus.FITTED
    return ColorFitResult(
        status=status,
        input_path=str(input_path),
        output_path=str(output_path) if fitted else None,
        input_size_bytes=20_000,
        output_size_bytes=8_000 if fitted else None,
        target_bytes=10_000,
        route=Route.VECTOR_COLOR.value,
        dpi=FIXED_COLOR_DPI,
        jpeg_quality=90,
        page_count=1,
        reasons=(f"color route returned {status.value}",),
    )


def test_skip_returns_success_without_calling_execution_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input.pdf"
    output = tmp_path / "output.pdf"
    diagnosis = _diagnosis(source, Route.SKIP)
    monkeypatch.setattr(
        "pdf_size_fit.fit.diagnose_pdf", lambda *args, **kwargs: diagnosis
    )

    def unexpected(*args: object, **kwargs: object) -> None:
        pytest.fail("an execution route was called")

    monkeypatch.setattr("pdf_size_fit.fit.fit_image_heavy_pdf", unexpected)
    monkeypatch.setattr("pdf_size_fit.fit.fit_monochrome_vector_pdf", unexpected)

    result = fit_pdf(source, output, target_bytes=10_000)

    assert result.status is FitStatus.ALREADY_BELOW_TARGET
    assert result.route is Route.SKIP
    assert result.output_path is None
    assert not output.exists()


def test_image_heavy_dispatches_only_to_image_route_and_forwards_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input.pdf"
    output = tmp_path / "output.pdf"
    diagnosis = _diagnosis(source, Route.IMAGE_HEAVY)
    monkeypatch.setattr(
        "pdf_size_fit.fit.diagnose_pdf", lambda *args, **kwargs: diagnosis
    )
    calls: list[tuple[object, ...]] = []

    def image_route(*args: object, **kwargs: object) -> ImageFitResult:
        calls.append((*args, kwargs))
        return _image_result(source, output)

    monkeypatch.setattr("pdf_size_fit.fit.fit_image_heavy_pdf", image_route)
    monkeypatch.setattr(
        "pdf_size_fit.fit.fit_monochrome_vector_pdf",
        lambda *args, **kwargs: pytest.fail("monochrome route was called"),
    )

    result = fit_pdf(
        source,
        output,
        target_bytes=10_000,
        min_quality=73,
        min_scale=0.81,
    )

    assert result.status is FitStatus.FITTED
    assert len(calls) == 1
    assert calls[0][0:2] == (source, output)
    assert calls[0][2] == {
        "target_bytes": 10_000,
        "min_quality": 73,
        "min_scale": 0.81,
    }


def test_vector_monochrome_dispatches_only_to_monochrome_and_forwards_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input.pdf"
    output = tmp_path / "output.pdf"
    diagnosis = _diagnosis(source, Route.VECTOR_MONOCHROME)
    monkeypatch.setattr(
        "pdf_size_fit.fit.diagnose_pdf", lambda *args, **kwargs: diagnosis
    )
    calls: list[tuple[object, ...]] = []

    def monochrome_route(*args: object, **kwargs: object) -> MonochromeFitResult:
        calls.append((*args, kwargs))
        return _monochrome_result(source, output)

    monkeypatch.setattr("pdf_size_fit.fit.fit_monochrome_vector_pdf", monochrome_route)
    monkeypatch.setattr(
        "pdf_size_fit.fit.fit_image_heavy_pdf",
        lambda *args, **kwargs: pytest.fail("image route was called"),
    )

    result = fit_pdf(
        source,
        output,
        target_bytes=10_000,
        allow_small_searchable_text_rasterization=True,
    )

    assert result.status is FitStatus.FITTED
    assert len(calls) == 1
    assert calls[0][0:2] == (source, output)
    assert calls[0][2] == {
        "target_bytes": 10_000,
        "dpi": 300,
        "allow_small_searchable_text_rasterization": True,
    }


@pytest.mark.parametrize("route", [Route.UNCLASSIFIED])
def test_unsupported_routes_fail_closed_without_output(
    route: Route, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input.pdf"
    output = tmp_path / "output.pdf"
    diagnosis = _diagnosis(source, route)
    monkeypatch.setattr(
        "pdf_size_fit.fit.diagnose_pdf", lambda *args, **kwargs: diagnosis
    )

    def unexpected(*args: object, **kwargs: object) -> None:
        pytest.fail("an execution route was called")

    monkeypatch.setattr("pdf_size_fit.fit.fit_image_heavy_pdf", unexpected)
    monkeypatch.setattr("pdf_size_fit.fit.fit_monochrome_vector_pdf", unexpected)

    result = fit_pdf(source, output, target_bytes=10_000)

    assert result.status is FitStatus.UNSUPPORTED_ROUTE
    assert result.route is route
    assert result.output_path is None
    assert result.delegated_route_status is None
    assert not output.exists()


def test_delegated_fitted_result_is_normalized_with_route_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input.pdf"
    output = tmp_path / "output.pdf"
    diagnosis = _diagnosis(source, Route.IMAGE_HEAVY)
    delegated = _image_result(source, output)
    monkeypatch.setattr(
        "pdf_size_fit.fit.diagnose_pdf", lambda *args, **kwargs: diagnosis
    )
    monkeypatch.setattr(
        "pdf_size_fit.fit.fit_image_heavy_pdf", lambda *args, **kwargs: delegated
    )

    result = fit_pdf(source, output, target_bytes=10_000)
    data = result.to_dict()

    assert result.status is FitStatus.FITTED
    assert result.output_size_bytes == 9_000
    assert result.delegated_route_status == "fitted"
    assert result.route_result is delegated
    assert data["route_result"]["selected_quality"] == 90
    assert data["reasons"] == (
        "diagnosed image-heavy",
        "image route returned fitted",
    )


def test_delegated_refusal_is_non_success_and_preserves_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input.pdf"
    output = tmp_path / "output.pdf"
    diagnosis = _diagnosis(source, Route.VECTOR_MONOCHROME)
    delegated = _monochrome_result(
        source, output, MonochromeFitStatus.UNSUPPORTED_DOCUMENT
    )
    monkeypatch.setattr(
        "pdf_size_fit.fit.diagnose_pdf", lambda *args, **kwargs: diagnosis
    )
    monkeypatch.setattr(
        "pdf_size_fit.fit.fit_monochrome_vector_pdf", lambda *args, **kwargs: delegated
    )

    result = fit_pdf(source, output, target_bytes=10_000)

    assert result.status is FitStatus.ROUTE_FAILED
    assert result.delegated_route_status == "unsupported-document"
    assert "monochrome route returned unsupported-document" in result.reasons
    assert result.route_result is delegated
    assert not output.exists()


def test_cli_json_is_machine_readable_and_success_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "input.pdf"
    output = tmp_path / "output.pdf"
    result = FitResult(
        status=FitStatus.FITTED,
        route=Route.IMAGE_HEAVY,
        input_path=str(source),
        output_path=str(output),
        input_size_bytes=20_000,
        output_size_bytes=9_000,
        target_bytes=10_000,
        delegated_route_status="fitted",
        reasons=("fitted",),
    )
    monkeypatch.setattr("pdf_size_fit.fit_cli.fit_pdf", lambda *args, **kwargs: result)

    exit_code = main([str(source), str(output), "--json"])
    data = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert data["status"] == "fitted"
    assert data["route"] == "image-heavy"


@pytest.mark.parametrize(
    "status", [FitStatus.UNSUPPORTED_ROUTE, FitStatus.ROUTE_FAILED]
)
def test_cli_non_success_exit_codes(
    status: FitStatus,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "input.pdf"
    output = tmp_path / "output.pdf"
    result = FitResult(
        status=status,
        route=Route.UNCLASSIFIED,
        input_path=str(source),
        output_path=None,
        input_size_bytes=20_000,
        output_size_bytes=None,
        target_bytes=10_000,
        delegated_route_status=None,
        reasons=("not fitted",),
    )
    monkeypatch.setattr("pdf_size_fit.fit_cli.fit_pdf", lambda *args, **kwargs: result)

    assert main([str(source), str(output), "--json"]) != 0
    capsys.readouterr()


def test_preexisting_destination_is_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input.pdf"
    output = tmp_path / "output.pdf"
    output.write_bytes(b"existing destination")
    original = output.read_bytes()
    monkeypatch.setattr(
        "pdf_size_fit.fit.diagnose_pdf",
        lambda *args, **kwargs: _diagnosis(source, Route.IMAGE_HEAVY),
    )

    with pytest.raises(FileExistsError, match="already exists"):
        fit_pdf(source, output, target_bytes=10_000)

    assert output.read_bytes() == original


@pytest.mark.parametrize(
    ("route", "route_attr", "result_func"),
    [
        (Route.IMAGE_HEAVY, "fit_image_heavy_pdf", _image_result),
        (Route.VECTOR_MONOCHROME, "fit_monochrome_vector_pdf", _monochrome_result),
        (Route.VECTOR_COLOR, "fit_color_vector_pdf", _color_result),
    ],
)
def test_fit_pdf_forwards_progress_callback(
    route: Route,
    route_attr: str,
    result_func: Callable[[Path, Path], Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.pdf"
    output = tmp_path / "output.pdf"
    diagnosis = _diagnosis(source, route)
    monkeypatch.setattr(
        "pdf_size_fit.fit.diagnose_pdf", lambda *args, **kwargs: diagnosis
    )
    passed_callback = None

    def mock_route(*args: object, **kwargs: object) -> Any:
        nonlocal passed_callback
        passed_callback = kwargs.get("progress_callback")
        return result_func(source, output)

    monkeypatch.setattr(f"pdf_size_fit.fit.{route_attr}", mock_route)

    dummy_callback = lambda e: None
    result = fit_pdf(
        source, output, target_bytes=10_000, progress_callback=dummy_callback
    )

    assert result.status is FitStatus.FITTED
    assert passed_callback is dummy_callback


@pytest.mark.parametrize(
    ("route", "route_attr", "result_func"),
    [
        (Route.IMAGE_HEAVY, "fit_image_heavy_pdf", _image_result),
        (Route.VECTOR_MONOCHROME, "fit_monochrome_vector_pdf", _monochrome_result),
        (Route.VECTOR_COLOR, "fit_color_vector_pdf", _color_result),
    ],
)
def test_fit_pdf_omits_progress_callback_when_none(
    route: Route,
    route_attr: str,
    result_func: Callable[[Path, Path], Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.pdf"
    output = tmp_path / "output.pdf"
    diagnosis = _diagnosis(source, route)
    monkeypatch.setattr(
        "pdf_size_fit.fit.diagnose_pdf", lambda *args, **kwargs: diagnosis
    )
    passed_kwargs: dict[str, object] = {}

    def mock_route(*args: object, **kwargs: object) -> Any:
        passed_kwargs.update(kwargs)
        return result_func(source, output)

    monkeypatch.setattr(f"pdf_size_fit.fit.{route_attr}", mock_route)

    result = fit_pdf(source, output, target_bytes=10_000)

    assert result.status is FitStatus.FITTED
    assert "progress_callback" not in passed_kwargs


def test_vector_color_dispatches_to_color_fit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input.pdf"
    output = tmp_path / "output.pdf"
    source.write_bytes(b"mock pdf")
    diagnosis = _diagnosis(source, Route.VECTOR_COLOR)
    monkeypatch.setattr(
        "pdf_size_fit.fit.diagnose_pdf", lambda *args, **kwargs: diagnosis
    )

    called = False

    def mock_fit(*args: object, **kwargs: object) -> ColorFitResult:
        nonlocal called
        called = True
        return ColorFitResult(
            status=ColorFitStatus.FITTED,
            input_path=str(source),
            output_path=str(output),
            input_size_bytes=8,
            output_size_bytes=4,
            target_bytes=10_000,
            route=Route.VECTOR_COLOR.value,
            dpi=FIXED_COLOR_DPI,
            jpeg_quality=90,
            page_count=1,
            reasons=("mock reason",),
        )

    monkeypatch.setattr("pdf_size_fit.fit.fit_color_vector_pdf", mock_fit)

    result = fit_pdf(source, output, target_bytes=10_000)

    assert called
    assert result.status is FitStatus.FITTED
    assert result.route is Route.VECTOR_COLOR
