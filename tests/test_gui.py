from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from pdf_size_fit.diagnose import Route
from pdf_size_fit.fit import FitResult, FitStatus
from pdf_size_fit.gui import (
    build_request,
    decimal_mb_to_bytes,
    present_error,
    present_result,
    run_request,
    suggest_output_path,
)


def _result(
    status: FitStatus,
    *,
    delegated_route_status: str | None = None,
) -> FitResult:
    output = "output.pdf" if status is FitStatus.FITTED else None
    return FitResult(
        status=status,
        route=Route.IMAGE_HEAVY,
        input_path="input.pdf",
        output_path=output,
        input_size_bytes=20_000_000,
        output_size_bytes=9_000_000 if output else None,
        target_bytes=10_000_000,
        delegated_route_status=delegated_route_status,
        reasons=("backend evidence",),
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
    assert "pause" in launcher.lower()
    assert metadata["project"]["gui-scripts"]["pdf-size-fit-gui"] == "pdf_size_fit.gui:main"
