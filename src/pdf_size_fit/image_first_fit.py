from __future__ import annotations

from math import ceil
from pathlib import Path
import shutil
import tempfile

from pypdf import PdfReader

from .diagnose import Route, diagnose_pdf
from .image_fit import (
    ImageFitAttempt,
    ImageFitResult,
    ImageFitStatus,
    UnsupportedImageError,
    _build_candidate,
    _find_redundant_opaque_smask_images,
    _has_pdfa_marker,
    _has_signature_structure,
    _verify_candidate,
)


# Standard mode deliberately uses a small probe set. The exact values are
# policy knobs that can be tuned from representative local benchmarks without
# changing the first-fit rule itself.
FIRST_FIT_QUALITY_PROBES = (100, 90, 75, 70)
FIRST_FIT_SCALE_PROBES_PERCENT = (90, 80, 70, 60, 50)


def _quality_probes(min_quality: int) -> tuple[int, ...]:
    values = [quality for quality in FIRST_FIT_QUALITY_PROBES if quality >= min_quality]
    if min_quality not in values:
        values.append(min_quality)
    return tuple(values)


def _scale_probes(min_scale: float) -> tuple[int, ...]:
    min_percent = max(1, ceil(min_scale * 100))
    if min_percent >= 100:
        return ()

    values = [
        percent
        for percent in FIRST_FIT_SCALE_PROBES_PERCENT
        if percent >= min_percent
    ]
    if min_percent not in values:
        values.append(min_percent)
    return tuple(values)


def fit_image_heavy_pdf_first_fit(
    input_path: str | Path,
    output_path: str | Path,
    *,
    target_bytes: int = 10_000_000,
    min_quality: int = 70,
    min_scale: float = 1.0,
) -> ImageFitResult:
    """Fit an image-heavy PDF using a bounded stop-on-first-success policy.

    This strategy reuses the existing image-route candidate builder, structural
    validation, signature/PDF-A refusal checks, soft-mask downsampling gate,
    and final verification. It changes only candidate ordering and the stopping
    rule. Every lossy candidate is rebuilt from the original input.
    """
    if target_bytes <= 0:
        raise ValueError("target_bytes must be greater than zero")
    if not 1 <= min_quality <= 100:
        raise ValueError("min_quality must be between 1 and 100")
    if not 0.0 < min_scale <= 1.0:
        raise ValueError("min_scale must be greater than 0 and at most 1")

    input_path = Path(input_path)
    output_path = Path(output_path)
    if input_path.resolve() == output_path.resolve():
        raise ValueError("output_path must differ from input_path")
    if output_path.exists():
        raise FileExistsError(f"output path already exists: {output_path}")

    input_size = input_path.stat().st_size
    diagnosis = diagnose_pdf(input_path, target_bytes=target_bytes)
    if diagnosis.route is Route.SKIP:
        return ImageFitResult(
            status=ImageFitStatus.ALREADY_BELOW_TARGET,
            input_path=str(input_path),
            output_path=None,
            input_size_bytes=input_size,
            output_size_bytes=None,
            target_bytes=target_bytes,
            selected_quality=None,
            images_replaced=0,
            attempts=(),
            reasons=(
                "input is already at or below the target size; no output was written",
            ),
        )
    if diagnosis.route is not Route.IMAGE_HEAVY:
        return ImageFitResult(
            status=ImageFitStatus.ROUTE_MISMATCH,
            input_path=str(input_path),
            output_path=None,
            input_size_bytes=input_size,
            output_size_bytes=None,
            target_bytes=target_bytes,
            selected_quality=None,
            images_replaced=0,
            attempts=(),
            reasons=(
                f"diagnosis proposed route {diagnosis.route.value!r}, not 'image-heavy'",
            ),
        )

    if _has_signature_structure(PdfReader(str(input_path))):
        return ImageFitResult(
            status=ImageFitStatus.SIGNED_PDF_UNSUPPORTED,
            input_path=str(input_path),
            output_path=None,
            input_size_bytes=input_size,
            output_size_bytes=None,
            target_bytes=target_bytes,
            selected_quality=None,
            images_replaced=0,
            attempts=(),
            reasons=(
                "PDF contains a signature field or certification permissions structure",
                "rewriting a signed PDF can invalidate signatures, so the current PoC writes no output",
            ),
        )

    if _has_pdfa_marker(PdfReader(str(input_path))):
        return ImageFitResult(
            status=ImageFitStatus.PDF_A_UNSUPPORTED,
            input_path=str(input_path),
            output_path=None,
            input_size_bytes=input_size,
            output_size_bytes=None,
            target_bytes=target_bytes,
            selected_quality=None,
            images_replaced=0,
            attempts=(),
            reasons=(
                "PDF contains PDF/A identification metadata",
                "the current PoC does not verify PDF/A conformance after rewriting, so no output is written",
            ),
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    attempts: list[ImageFitAttempt] = []
    selected_candidate: Path | None = None
    selected_quality: int | None = None
    selected_replaced = 0
    selected_scale: float | None = None
    removable_opaque_smask_refs: frozenset[tuple[int, int]] = frozenset()

    try:
        with tempfile.TemporaryDirectory(prefix="pdf-size-fit-first-") as temp_dir_name:
            temp_dir = Path(temp_dir_name)

            def measure(scale_percent: int, quality: int) -> tuple[Path, int, int]:
                scale = scale_percent / 100.0
                candidate = temp_dir / f"candidate-s{scale_percent:03d}-q{quality}.pdf"
                replaced = _build_candidate(
                    input_path,
                    candidate,
                    quality=quality,
                    scale=scale,
                    removable_opaque_smask_refs=removable_opaque_smask_refs,
                )
                _verify_candidate(input_path, candidate)
                size = candidate.stat().st_size
                attempts.append(
                    ImageFitAttempt(quality=quality, size_bytes=size, scale=scale)
                )
                return candidate, size, replaced

            try:
                for quality in _quality_probes(min_quality):
                    candidate, size, replaced = measure(100, quality)
                    if size <= target_bytes:
                        selected_candidate = candidate
                        selected_quality = quality
                        selected_replaced = replaced
                        selected_scale = 1.0
                        break
            except UnsupportedImageError as exc:
                return ImageFitResult(
                    status=ImageFitStatus.UNSUPPORTED_IMAGE,
                    input_path=str(input_path),
                    output_path=None,
                    input_size_bytes=input_size,
                    output_size_bytes=None,
                    target_bytes=target_bytes,
                    selected_quality=None,
                    images_replaced=0,
                    attempts=tuple(attempts),
                    reasons=(
                        str(exc),
                        "input was left unchanged and no output was written",
                    ),
                )

            if selected_candidate is None and min_scale < 1.0:
                try:
                    removable_opaque_smask_refs = _find_redundant_opaque_smask_images(
                        input_path
                    )
                    for scale_percent in _scale_probes(min_scale):
                        candidate, size, replaced = measure(scale_percent, min_quality)
                        if size <= target_bytes:
                            selected_candidate = candidate
                            selected_quality = min_quality
                            selected_replaced = replaced
                            selected_scale = scale_percent / 100.0
                            break
                except UnsupportedImageError as exc:
                    return ImageFitResult(
                        status=ImageFitStatus.UNSUPPORTED_IMAGE,
                        input_path=str(input_path),
                        output_path=None,
                        input_size_bytes=input_size,
                        output_size_bytes=None,
                        target_bytes=target_bytes,
                        selected_quality=None,
                        images_replaced=0,
                        attempts=tuple(attempts),
                        reasons=(
                            str(exc),
                            "full-resolution first-fit probes did not meet the target and the downsampling fallback is unsafe for this image structure",
                            "input was left unchanged and no output was written",
                        ),
                    )

            if (
                selected_candidate is None
                or selected_quality is None
                or selected_scale is None
            ):
                return ImageFitResult(
                    status=ImageFitStatus.TARGET_NOT_MET,
                    input_path=str(input_path),
                    output_path=None,
                    input_size_bytes=input_size,
                    output_size_bytes=None,
                    target_bytes=target_bytes,
                    selected_quality=None,
                    images_replaced=0,
                    attempts=tuple(attempts),
                    reasons=(
                        f"bounded first-fit probes did not meet the target at or above JPEG quality {min_quality} and image scale {min_scale:.0%}",
                        "no output was written; another compression route or user-visible fallback is required",
                    ),
                )

            shutil.copyfile(selected_candidate, output_path)
    except Exception:
        if output_path.exists():
            output_path.unlink()
        raise

    _verify_candidate(input_path, output_path)
    final_size = output_path.stat().st_size
    if final_size > target_bytes:
        output_path.unlink(missing_ok=True)
        raise RuntimeError("selected output unexpectedly exceeds target after final copy")

    if selected_scale < 1.0:
        fit_reason = (
            f"bounded first-fit met target at {selected_scale:.0%} image scale "
            f"and JPEG quality {selected_quality}"
        )
    else:
        fit_reason = (
            "bounded first-fit met target at full image resolution and JPEG quality "
            f"{selected_quality}"
        )

    result_reasons = [
        fit_reason,
        f"standard first-fit stopped after {len(attempts)} validated candidate(s)",
        "each candidate was rebuilt from the original PDF; lossy recompression was not cumulative",
        "page count, media boxes, and rotation were verified before accepting the output",
    ]
    if selected_scale < 1.0 and removable_opaque_smask_refs:
        result_reasons.append(
            f"removed {len(removable_opaque_smask_refs)} redundant fully opaque /SMask reference(s) before downsampling"
        )

    return ImageFitResult(
        status=ImageFitStatus.FITTED,
        input_path=str(input_path),
        output_path=str(output_path),
        input_size_bytes=input_size,
        output_size_bytes=final_size,
        target_bytes=target_bytes,
        selected_quality=selected_quality,
        images_replaced=selected_replaced,
        attempts=tuple(attempts),
        reasons=tuple(result_reasons),
        selected_scale=selected_scale,
    )
