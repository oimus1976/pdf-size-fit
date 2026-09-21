from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from pypdf import PdfWriter

import pdf_size_fit.gui as gui
from pdf_size_fit.diagnose import Route
from pdf_size_fit.fit import FitResult, FitStatus
from pdf_size_fit.image_fit import ImageFitResult, ImageFitStatus
from pdf_size_fit.gui import (
    ALREADY_BELOW_MESSAGE,
    GuiRequest,
    SIMPLE_MIN_SCALE,
    SIMPLE_TARGET_BYTES,
    build_request,
    build_simple_request,
    decimal_mb_to_bytes,
    parse_drop_paths,
    present_error,
    present_result,
    present_simple_result,
    run_request,
    run_simple_input,
    run_simple_request,
    suggest_output_path,
)


def _result(
    status: FitStatus,
    *,
    delegated_route_status: str | None = None,
    route: Route = Route.IMAGE_HEAVY,
    route_result: ImageFitResult | None = None,
) -> FitResult:
    output = "output.pdf" if status is FitStatus.FITTED else None
    return FitResult(
        status=status,
        route=route,
        input_path="input.pdf",
        output_path=output,
        input_size_bytes=20_000_000,
        output_size_bytes=9_000_000 if output else None,
        target_bytes=10_000_000,
        delegated_route_status=delegated_route_status,
        reasons=("backend evidence",),
        route_result=route_result,
    )


def test_output_suggestion_avoids_input_and_existing_files(tmp_path: Path) -> None:
    source = tmp_path / "sample.pdf"
    source.write_bytes(b"input")
    first = tmp_path / "sample-fit.pdf"
    second = tmp_path / "sample-fit-2.pdf"
    first.write_bytes(b"existing")
    second.write_bytes(b"existing")

    suggested = suggest_output_path(source)

    assert suggested == tmp_path / "sample-fit-3.pdf"
    assert suggested.resolve() != source.resolve()
    assert not suggested.exists()


@pytest.mark.parametrize(
    ("value", "expected"),
    [("10", 10_000_000), ("0.5", 500_000), ("1.000001", 1_000_001)],
)
def test_decimal_mb_to_bytes(value: str, expected: int) -> None:
    assert decimal_mb_to_bytes(value) == expected


@pytest.mark.parametrize("value", ["", "abc", "0", "-1", "NaN", "Infinity", "0.0000001"])
def test_decimal_mb_to_bytes_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        decimal_mb_to_bytes(value)


def test_gui_request_maps_exactly_to_fit_pdf_arguments(tmp_path: Path) -> None:
    source = tmp_path / "input.pdf"
    source.write_bytes(b"synthetic")
    output = tmp_path / "output.pdf"
    request = build_request(
        str(source), str(output), "10", "73", "81", True
    )
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fitter(*args: object, **kwargs: object) -> FitResult:
        calls.append((args, kwargs))
        return _result(FitStatus.FITTED, delegated_route_status="fitted")

    run_request(request, fitter=fitter)

    assert calls == [
        (
            (source, output),
            {
                "target_bytes": 10_000_000,
                "min_quality": 73,
                "min_scale": 0.81,
                "allow_small_searchable_text_rasterization": True,
            },
        )
    ]


def test_gui_request_preserves_safe_defaults(tmp_path: Path) -> None:
    source = tmp_path / "input.pdf"
    source.write_bytes(b"synthetic")
    request = build_request(
        str(source), str(tmp_path / "output.pdf"), "10", "70", "100", False
    )
    assert request.target_bytes == 10_000_000
    assert request.min_quality == 70
    assert request.min_scale == 1.0
    assert request.allow_small_searchable_text_rasterization is False


def test_simple_request_fixes_target_and_scale_floor(tmp_path: Path) -> None:
    source = tmp_path / "input.pdf"
    source.write_bytes(b"synthetic")

    request = build_simple_request(source)

    assert SIMPLE_TARGET_BYTES == 10_000_000
    assert SIMPLE_MIN_SCALE == 0.50
    assert request.target_bytes == 10_000_000
    assert request.min_quality == 70
    assert request.min_scale == 0.50
    assert request.allow_small_searchable_text_rasterization is False
    assert request.output_path == tmp_path / "input-fit.pdf"


def test_auto_downsampled_success_reports_selected_scale_and_quality(tmp_path: Path) -> None:
    output = tmp_path / "oversized-fit-2.pdf"
    route_result = ImageFitResult(
        status=ImageFitStatus.FITTED,
        input_path=str(tmp_path / "oversized.pdf"),
        output_path=str(output),
        input_size_bytes=20_000_000,
        output_size_bytes=9_000_000,
        target_bytes=10_000_000,
        selected_quality=70,
        images_replaced=1,
        attempts=(),
        reasons=("scaled",),
        selected_scale=0.83,
    )
    result = FitResult(
        status=FitStatus.FITTED,
        route=Route.IMAGE_HEAVY,
        input_path=route_result.input_path,
        output_path=route_result.output_path,
        input_size_bytes=route_result.input_size_bytes,
        output_size_bytes=route_result.output_size_bytes,
        target_bytes=route_result.target_bytes,
        delegated_route_status="fitted",
        reasons=("backend evidence",),
        route_result=route_result,
    )

    presentation = present_simple_result(result)

    assert presentation.successful_output == output
    assert "画像スケール: 83%" in presentation.summary
    assert "JPEG 品質: 70" in presentation.summary
    assert "画質が低下" in presentation.summary
    assert '"selected_scale": 0.83' in presentation.details


def test_full_resolution_fit_presentation_does_not_claim_scale_reduction(tmp_path: Path) -> None:
    output = tmp_path / "oversized-fit.pdf"
    route_result = ImageFitResult(
        status=ImageFitStatus.FITTED,
        input_path=str(tmp_path / "oversized.pdf"),
        output_path=str(output),
        input_size_bytes=20_000_000,
        output_size_bytes=9_000_000,
        target_bytes=10_000_000,
        selected_quality=90,
        images_replaced=1,
        attempts=(),
        reasons=("unscaled",),
        selected_scale=1.0,
    )
    result = FitResult(
        status=FitStatus.FITTED,
        route=Route.IMAGE_HEAVY,
        input_path=route_result.input_path,
        output_path=route_result.output_path,
        input_size_bytes=route_result.input_size_bytes,
        output_size_bytes=route_result.output_size_bytes,
        target_bytes=route_result.target_bytes,
        delegated_route_status="fitted",
        reasons=("backend evidence",),
        route_result=route_result,
    )

    presentation = present_simple_result(result)

    assert presentation.successful_output == output
    assert "画質が低下" not in presentation.summary
    assert "画像スケール" not in presentation.summary


def test_simple_target_not_met_creates_no_output_file(tmp_path: Path) -> None:
    result = _result(FitStatus.ROUTE_FAILED, delegated_route_status="target-not-met")
    presentation = present_simple_result(result)

    assert presentation.category == "target-not-met"
    assert presentation.successful_output is None
    assert presentation.title == "10MB以下にできませんでした。"
    assert "出力ファイルは作成していません" in presentation.summary
    assert not (tmp_path / "output.pdf").exists()


@pytest.mark.parametrize("route", [Route.IMAGE_HEAVY, Route.VECTOR_COLOR, Route.VECTOR_MONOCHROME])
def test_non_image_and_image_target_not_met_get_route_neutral_wording(route: Route) -> None:
    result = _result(
        FitStatus.ROUTE_FAILED,
        delegated_route_status="target-not-met",
        route=route,
    )
    presentation = present_simple_result(result)

    assert presentation.title == "10MB以下にできませんでした。"
    assert "画像" not in presentation.title
    assert "縮小" not in presentation.title


def test_simple_small_pdf_returns_exact_no_conversion_message_and_no_output(
    tmp_path: Path,
) -> None:
    source = tmp_path / "small.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with source.open("wb") as stream:
        writer.write(stream)

    expected_output = tmp_path / "small-fit.pdf"
    result = run_simple_input(source)
    presentation = present_simple_result(result)

    assert result.status is FitStatus.ALREADY_BELOW_TARGET
    assert presentation.title == ALREADY_BELOW_MESSAGE
    assert not expected_output.exists()


def test_simple_exact_boundary_does_not_call_backend(tmp_path: Path) -> None:
    source = tmp_path / "exactly-10mb.pdf"
    source.write_bytes(b"%PDF-1.4\n" + b"0" * (10_000_000 - 9))
    request = build_simple_request(source)

    def unexpected(*args: object, **kwargs: object) -> FitResult:
        pytest.fail("fit_pdf must not run for a file at the simple-mode limit")

    result = run_simple_request(request, fitter=unexpected)

    assert result.status is FitStatus.ALREADY_BELOW_TARGET
    assert result.input_size_bytes == 10_000_000
    assert result.output_path is None
    assert not request.output_path.exists()


def test_simple_oversized_input_maps_to_integrated_backend_once(tmp_path: Path) -> None:
    source = tmp_path / "oversized.pdf"
    with source.open("wb") as stream:
        stream.truncate(10_000_001)
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fitter(*args: object, **kwargs: object) -> FitResult:
        calls.append((args, kwargs))
        return _result(FitStatus.FITTED, delegated_route_status="fitted")

    run_simple_input(source, fitter=fitter)

    assert calls == [
        (
            (source, tmp_path / "oversized-fit.pdf"),
            {
                "target_bytes": 10_000_000,
                "min_quality": 70,
                "min_scale": 0.50,
                "allow_small_searchable_text_rasterization": False,
            },
        )
    ]


def test_target_not_met_results_in_exactly_one_backend_call_and_no_retry(tmp_path: Path) -> None:
    source = tmp_path / "oversized.pdf"
    with source.open("wb") as stream:
        stream.truncate(10_000_001)
    calls = 0

    def fitter(*args: object, **kwargs: object) -> FitResult:
        nonlocal calls
        calls += 1
        return _result(FitStatus.ROUTE_FAILED, delegated_route_status="target-not-met")

    result = run_simple_input(source, fitter=fitter)

    assert calls == 1
    assert result.status is FitStatus.ROUTE_FAILED
    assert result.delegated_route_status == "target-not-met"


def test_hard_refusal_results_in_exactly_one_backend_call_and_no_retry(tmp_path: Path) -> None:
    source = tmp_path / "oversized.pdf"
    with source.open("wb") as stream:
        stream.truncate(10_000_001)
    calls = 0

    def fitter(*args: object, **kwargs: object) -> FitResult:
        nonlocal calls
        calls += 1
        return _result(FitStatus.ROUTE_FAILED, delegated_route_status="unsupported-document")

    result = run_simple_input(source, fitter=fitter)

    assert calls == 1
    assert result.status is FitStatus.ROUTE_FAILED
    assert result.delegated_route_status == "unsupported-document"


def test_obsolete_fallback_helpers_and_constants_are_absent() -> None:
    assert not hasattr(gui, "DOWNSAMPLING_FALLBACK_MIN_SCALE")
    assert not hasattr(gui, "is_simple_mode_request")
    assert not hasattr(gui, "should_offer_downsampling")
    assert not hasattr(gui, "build_downsampling_fallback_request")
    assert not hasattr(gui, "run_downsampling_fallback_if_confirmed")
    assert not hasattr(gui._Application, "_confirm_downsampling")


def test_shell_argument_and_gui_drop_use_the_same_simple_backend_path(tmp_path: Path) -> None:
    source = tmp_path / "name with spaces.pdf"
    with source.open("wb") as stream:
        stream.truncate(10_000_001)
    drop_paths = parse_drop_paths(
        "{name with spaces.pdf}", lambda _data: (str(source),)
    )
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fitter(*args: object, **kwargs: object) -> FitResult:
        calls.append((args, kwargs))
        return _result(FitStatus.FITTED, delegated_route_status="fitted")

    run_simple_input(source, fitter=fitter)  # shell/startup argument
    run_simple_input(drop_paths[0], fitter=fitter)  # GUI DND event

    assert len(calls) == 2
    assert calls[0] == calls[1]


def test_simple_presentation_hides_backend_controls_and_route() -> None:
    presentation = present_simple_result(
        _result(FitStatus.FITTED, delegated_route_status="fitted")
    )
    visible = presentation.title + presentation.summary

    assert "quality" not in visible.lower()
    assert "scale" not in visible.lower()
    assert "route" not in visible.lower()
    assert "ルート" not in visible


def test_gui_request_rejects_input_or_existing_output_as_destination(tmp_path: Path) -> None:
    source = tmp_path / "input.pdf"
    source.write_bytes(b"synthetic")
    existing = tmp_path / "existing.pdf"
    existing.write_bytes(b"keep me")

    for destination in (source, existing):
        with pytest.raises(ValueError):
            build_request(str(source), str(destination), "10", "70", "100", False)
    assert source.read_bytes() == b"synthetic"
    assert existing.read_bytes() == b"keep me"


@pytest.mark.parametrize(
    ("status", "delegated", "category", "japanese_text"),
    [
        (FitStatus.FITTED, "fitted", "fitted", "変換しました"),
        (FitStatus.ALREADY_BELOW_TARGET, None, "already-below-target", "作成していません"),
        (FitStatus.UNSUPPORTED_ROUTE, None, "unsupported-route", "未対応"),
        (FitStatus.ROUTE_FAILED, "target-not-met", "target-not-met", "到達"),
        (FitStatus.ROUTE_FAILED, "unsupported-document", "delegated-refusal", "拒否"),
    ],
)
def test_backend_statuses_map_to_user_facing_results(
    status: FitStatus,
    delegated: str | None,
    category: str,
    japanese_text: str,
) -> None:
    presentation = present_result(
        _result(status, delegated_route_status=delegated)
    )
    assert presentation.category == category
    assert japanese_text in presentation.title + presentation.summary
    assert "backend evidence" in presentation.details


def test_unexpected_error_has_japanese_status_and_details() -> None:
    presentation = present_error(RuntimeError("boom"))
    assert presentation.category == "unexpected-error"
    assert "予期しないエラー" in presentation.title
    assert "RuntimeError: boom" in presentation.details


def test_launcher_and_gui_entry_point_exist() -> None:
    root = Path(__file__).parents[1]
    launcher = (root / "start-pdf-size-fit.cmd").read_text(encoding="utf-8")
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))

    assert ".venv\\Scripts\\pythonw.exe" in launcher
    assert "-m pdf_size_fit.gui %*" in launcher
    assert "pause" in launcher.lower()
    assert metadata["project"]["gui-scripts"]["pdf-size-fit-gui"] == "pdf_size_fit.gui:main"
    assert any(
        dependency.startswith("tkinterdnd2")
        for dependency in metadata["project"]["dependencies"]
    )
