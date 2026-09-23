from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .diagnose import Diagnosis, Route, diagnose_pdf
from .color_fit import (
    FIXED_COLOR_DPI,
    ColorFitResult,
    ColorFitStatus,
    fit_color_vector_pdf,
)
from .image_first_fit import fit_image_heavy_pdf_first_fit
from .image_fit import (
    ImageFitResult,
    ImageFitStatus,
    fit_image_heavy_pdf as fit_image_heavy_pdf_best_fit,
)
from .monochrome_fit import (
    FIXED_DPI,
    MonochromeFitResult,
    MonochromeFitStatus,
    fit_monochrome_vector_pdf,
)
from .progress import ProgressCallback


class FitMode(str, Enum):
    STANDARD = "standard"
    HIGH_QUALITY = "high-quality"


class FitStatus(str, Enum):
    FITTED = "fitted"
    ALREADY_BELOW_TARGET = "already-below-target"
    UNSUPPORTED_ROUTE = "unsupported-route"
    UNSUPPORTED_MODE = "unsupported-mode"
    ROUTE_FAILED = "route-failed"


RouteResult = ImageFitResult | MonochromeFitResult | ColorFitResult


@dataclass(frozen=True)
class FitResult:
    status: FitStatus
    route: Route
    input_path: str
    output_path: str | None
    input_size_bytes: int
    output_size_bytes: int | None
    target_bytes: int
    delegated_route_status: str | None
    reasons: tuple[str, ...]
    route_result: RouteResult | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "route": self.route.value,
            "input_path": self.input_path,
            "output_path": self.output_path,
            "input_size_bytes": self.input_size_bytes,
            "output_size_bytes": self.output_size_bytes,
            "target_bytes": self.target_bytes,
            "delegated_route_status": self.delegated_route_status,
            "reasons": self.reasons,
            "route_result": (
                self.route_result.to_dict() if self.route_result is not None else None
            ),
        }


def _normalize_route_result(diagnosis: Diagnosis, result: RouteResult) -> FitResult:
    if (
        (isinstance(result, ImageFitResult) and result.status is ImageFitStatus.FITTED)
        or (
            isinstance(result, MonochromeFitResult)
            and result.status is MonochromeFitStatus.FITTED
        )
        or (
            isinstance(result, ColorFitResult)
            and result.status is ColorFitStatus.FITTED
        )
    ):
        status = FitStatus.FITTED
    elif (
        (
            isinstance(result, ImageFitResult)
            and result.status is ImageFitStatus.ALREADY_BELOW_TARGET
        )
        or (
            isinstance(result, MonochromeFitResult)
            and result.status is MonochromeFitStatus.SKIP
        )
        or (isinstance(result, ColorFitResult) and result.status is ColorFitStatus.SKIP)
    ):
        status = FitStatus.ALREADY_BELOW_TARGET
    else:
        status = FitStatus.ROUTE_FAILED

    return FitResult(
        status=status,
        route=diagnosis.route,
        input_path=result.input_path,
        output_path=result.output_path,
        input_size_bytes=result.input_size_bytes,
        output_size_bytes=result.output_size_bytes,
        target_bytes=result.target_bytes,
        delegated_route_status=result.status.value,
        reasons=diagnosis.reasons + result.reasons,
        route_result=result,
    )


def fit_pdf(
    input_path: str | Path,
    output_path: str | Path,
    *,
    target_bytes: int = 10_000_000,
    mode: FitMode = FitMode.STANDARD,
    min_quality: int = 70,
    min_scale: float = 1.0,
    allow_small_searchable_text_rasterization: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> FitResult:
    if not isinstance(mode, FitMode):
        raise TypeError("mode must be a FitMode")

    if target_bytes <= 0:
        raise ValueError("target_bytes must be greater than zero")

    if mode is FitMode.HIGH_QUALITY:
        if min_quality < 70:
            raise ValueError("min_quality must be at least 70 in high-quality mode")
        if min_scale < 0.50:
            raise ValueError("min_scale must be at least 0.50 in high-quality mode")

    input_path = Path(input_path)
    output_path = Path(output_path)
    if input_path.resolve() == output_path.resolve():
        raise ValueError("output_path must differ from input_path")
    if output_path.exists():
        raise FileExistsError(f"output path already exists: {output_path}")

    diagnosis = diagnose_pdf(input_path, target_bytes=target_bytes)

    if diagnosis.route is Route.SKIP:
        return FitResult(
            status=FitStatus.ALREADY_BELOW_TARGET,
            route=diagnosis.route,
            input_path=str(input_path),
            output_path=None,
            input_size_bytes=diagnosis.file_size_bytes,
            output_size_bytes=None,
            target_bytes=target_bytes,
            delegated_route_status=None,
            reasons=diagnosis.reasons,
        )

    if mode is FitMode.HIGH_QUALITY:
        if diagnosis.route is Route.IMAGE_HEAVY:
            image_kwargs: dict[str, Any] = {
                "target_bytes": target_bytes,
                "min_quality": min_quality,
                "min_scale": min_scale,
            }
            if progress_callback is not None:
                image_kwargs["progress_callback"] = progress_callback
            route_result = fit_image_heavy_pdf_best_fit(
                input_path,
                output_path,
                **image_kwargs,
            )
            return _normalize_route_result(diagnosis, route_result)

        if diagnosis.route in (Route.VECTOR_MONOCHROME, Route.VECTOR_COLOR):
            return FitResult(
                status=FitStatus.UNSUPPORTED_MODE,
                route=diagnosis.route,
                input_path=str(input_path),
                output_path=None,
                input_size_bytes=diagnosis.file_size_bytes,
                output_size_bytes=None,
                target_bytes=target_bytes,
                delegated_route_status=None,
                reasons=diagnosis.reasons
                + (
                    "high-quality mode is currently supported for image-heavy PDFs only; no output was written",
                    "please retry using standard mode",
                ),
            )

        return FitResult(
            status=FitStatus.UNSUPPORTED_ROUTE,
            route=diagnosis.route,
            input_path=str(input_path),
            output_path=None,
            input_size_bytes=diagnosis.file_size_bytes,
            output_size_bytes=None,
            target_bytes=target_bytes,
            delegated_route_status=None,
            reasons=diagnosis.reasons
            + (
                f"route {diagnosis.route.value!r} has no supported execution path; no output was written",
            ),
        )

    if diagnosis.route is Route.IMAGE_HEAVY:
        image_kwargs = {
            "target_bytes": target_bytes,
            "min_quality": min_quality,
            "min_scale": min_scale,
        }
        if progress_callback is not None:
            image_kwargs["progress_callback"] = progress_callback
        route_result = fit_image_heavy_pdf_first_fit(
            input_path,
            output_path,
            **image_kwargs,
        )
        return _normalize_route_result(diagnosis, route_result)

    if diagnosis.route is Route.VECTOR_MONOCHROME:
        mono_kwargs: dict[str, Any] = {
            "target_bytes": target_bytes,
            "dpi": FIXED_DPI,
            "allow_small_searchable_text_rasterization": (
                allow_small_searchable_text_rasterization
            ),
        }
        if progress_callback is not None:
            mono_kwargs["progress_callback"] = progress_callback
        route_result = fit_monochrome_vector_pdf(
            input_path,
            output_path,
            **mono_kwargs,
        )
        return _normalize_route_result(diagnosis, route_result)

    if diagnosis.route is Route.VECTOR_COLOR:
        color_kwargs: dict[str, Any] = {
            "target_bytes": target_bytes,
            "dpi": FIXED_COLOR_DPI,
            "jpeg_quality": 90,
            "allow_small_searchable_text_rasterization": (
                allow_small_searchable_text_rasterization
            ),
        }
        if progress_callback is not None:
            color_kwargs["progress_callback"] = progress_callback
        route_result = fit_color_vector_pdf(
            input_path,
            output_path,
            **color_kwargs,
        )
        return _normalize_route_result(diagnosis, route_result)

    return FitResult(
        status=FitStatus.UNSUPPORTED_ROUTE,
        route=diagnosis.route,
        input_path=str(input_path),
        output_path=None,
        input_size_bytes=diagnosis.file_size_bytes,
        output_size_bytes=None,
        target_bytes=target_bytes,
        delegated_route_status=None,
        reasons=diagnosis.reasons
        + (
            f"route {diagnosis.route.value!r} has no supported execution path; no output was written",
        ),
    )
