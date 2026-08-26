from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
import shutil
import tempfile
from typing import Any

from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import IndirectObject, NameObject, StreamObject

from .diagnose import Route, diagnose_pdf


class ImageFitStatus(str, Enum):
    FITTED = "fitted"
    ALREADY_BELOW_TARGET = "already-below-target"
    ROUTE_MISMATCH = "route-mismatch"
    UNSUPPORTED_IMAGE = "unsupported-image"
    TARGET_NOT_MET = "target-not-met"


@dataclass(frozen=True)
class ImageFitAttempt:
    quality: int
    size_bytes: int


@dataclass(frozen=True)
class ImageFitResult:
    status: ImageFitStatus
    input_path: str
    output_path: str | None
    input_size_bytes: int
    output_size_bytes: int | None
    target_bytes: int
    selected_quality: int | None
    images_replaced: int
    attempts: tuple[ImageFitAttempt, ...]
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


class UnsupportedImageError(RuntimeError):
    pass


def _ref_key(ref: IndirectObject) -> tuple[int, int]:
    return ref.idnum, ref.generation


def _simple_colorspace(obj: StreamObject) -> str | None:
    colorspace = obj.get("/ColorSpace")
    if isinstance(colorspace, IndirectObject):
        colorspace = colorspace.get_object()
    if colorspace in ("/DeviceRGB", "/DeviceGray"):
        return str(colorspace)
    return None


def _validate_image_for_replacement(img: Any) -> tuple[IndirectObject, Any | None]:
    ref = img.indirect_reference
    if ref is None:
        raise UnsupportedImageError("inline images cannot be replaced with pypdf ImageFile.replace()")

    obj = ref.get_object()
    if not isinstance(obj, StreamObject) or obj.get("/Subtype") != "/Image":
        raise UnsupportedImageError("encountered an image entry that is not an image XObject stream")

    if _simple_colorspace(obj) is None:
        raise UnsupportedImageError(f"unsupported image color space: {obj.get('/ColorSpace')!r}")

    if obj.get("/BitsPerComponent") != 8:
        raise UnsupportedImageError(
            f"unsupported bits per component: {obj.get('/BitsPerComponent')!r}; current PoC accepts 8-bit images"
        )

    if "/Mask" in obj:
        raise UnsupportedImageError("color-key /Mask images are not supported by the current PoC")
    if "/Decode" in obj:
        raise UnsupportedImageError("images with a custom /Decode array are not supported by the current PoC")

    smask = obj.get("/SMask")
    if smask is not None:
        smask_obj = smask.get_object() if isinstance(smask, IndirectObject) else smask
        if not isinstance(smask_obj, StreamObject):
            raise UnsupportedImageError("/SMask is not a stream")
        if smask_obj.get("/Width") != obj.get("/Width") or smask_obj.get("/Height") != obj.get("/Height"):
            raise UnsupportedImageError("/SMask dimensions do not match the base image")

    if img.image is None:
        raise UnsupportedImageError("pypdf could not decode an image XObject through Pillow")

    return ref, smask


def _base_image_for_jpeg(image: Image.Image, *, has_smask: bool) -> Image.Image:
    if image.mode == "RGB":
        return image
    if image.mode == "L":
        return image
    if has_smask:
        if image.mode == "LA":
            return image.getchannel("L")
        return image.convert("RGB")
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        raise UnsupportedImageError("transparent image has no reusable /SMask")
    return image.convert("RGB")


def _build_candidate(input_path: Path, output_path: Path, *, quality: int) -> int:
    writer = PdfWriter(clone_from=str(input_path))
    seen: set[tuple[int, int]] = set()
    replaced = 0

    for page in writer.pages:
        for img in page.images:
            if img.indirect_reference is None:
                continue

            key = _ref_key(img.indirect_reference)
            if key in seen:
                continue
            seen.add(key)

            ref, smask = _validate_image_for_replacement(img)
            replacement = _base_image_for_jpeg(img.image, has_smask=smask is not None)
            try:
                img.replace(replacement, quality=quality, subsampling=0)
            except Exception as exc:
                raise UnsupportedImageError(
                    f"image replacement failed for {img.name}: {type(exc).__name__}: {exc}"
                ) from exc

            if smask is not None:
                ref.get_object()[NameObject("/SMask")] = smask

            replaced += 1

    if replaced == 0:
        raise UnsupportedImageError("no replaceable image XObjects were found")

    with output_path.open("wb") as f:
        writer.write(f)
    return replaced


def _page_signature(reader: PdfReader) -> tuple[tuple[float, float, float, float, int], ...]:
    sig = []
    for page in reader.pages:
        box = page.mediabox
        sig.append(
            (
                float(box.left),
                float(box.bottom),
                float(box.right),
                float(box.top),
                int(page.get("/Rotate", 0) or 0),
            )
        )
    return tuple(sig)


def _verify_candidate(input_path: Path, candidate_path: Path) -> None:
    source = PdfReader(str(input_path))
    candidate = PdfReader(str(candidate_path))
    if len(source.pages) != len(candidate.pages):
        raise RuntimeError("candidate page count differs from input")
    if _page_signature(source) != _page_signature(candidate):
        raise RuntimeError("candidate page dimensions or rotation differ from input")


def _quality_probes(min_quality: int) -> tuple[int, ...]:
    coarse = [100, 95, 90, 85, 80, 75, 70, 65, 60, 55, 50]
    values = [q for q in coarse if q >= min_quality]
    if min_quality not in values:
        values.append(min_quality)
    return tuple(values)


def fit_image_heavy_pdf(
    input_path: str | Path,
    output_path: str | Path,
    *,
    target_bytes: int = 10_000_000,
    min_quality: int = 70,
) -> ImageFitResult:
    if target_bytes <= 0:
        raise ValueError("target_bytes must be greater than zero")
    if not 1 <= min_quality <= 100:
        raise ValueError("min_quality must be between 1 and 100")

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
            input_path=str(input_path), output_path=None,
            input_size_bytes=input_size, output_size_bytes=None,
            target_bytes=target_bytes, selected_quality=None,
            images_replaced=0, attempts=(),
            reasons=("input is already at or below the target size; no output was written",),
        )
    if diagnosis.route is not Route.IMAGE_HEAVY:
        return ImageFitResult(
            status=ImageFitStatus.ROUTE_MISMATCH,
            input_path=str(input_path), output_path=None,
            input_size_bytes=input_size, output_size_bytes=None,
            target_bytes=target_bytes, selected_quality=None,
            images_replaced=0, attempts=(),
            reasons=(f"diagnosis proposed route {diagnosis.route.value!r}, not 'image-heavy'",),
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    attempts: list[ImageFitAttempt] = []
    best_candidate: Path | None = None
    best_quality: int | None = None
    best_size: int | None = None
    best_replaced = 0

    try:
        with tempfile.TemporaryDirectory(prefix="pdf-size-fit-") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            previous_over_quality: int | None = None

            for quality in _quality_probes(min_quality):
                candidate = temp_dir / f"candidate-q{quality}.pdf"
                try:
                    replaced = _build_candidate(input_path, candidate, quality=quality)
                except UnsupportedImageError as exc:
                    return ImageFitResult(
                        status=ImageFitStatus.UNSUPPORTED_IMAGE,
                        input_path=str(input_path), output_path=None,
                        input_size_bytes=input_size, output_size_bytes=None,
                        target_bytes=target_bytes, selected_quality=None,
                        images_replaced=0, attempts=tuple(attempts),
                        reasons=(str(exc), "input was left unchanged and no output was written"),
                    )

                _verify_candidate(input_path, candidate)
                size = candidate.stat().st_size
                attempts.append(ImageFitAttempt(quality=quality, size_bytes=size))

                if size <= target_bytes:
                    best_candidate = candidate
                    best_quality = quality
                    best_size = size
                    best_replaced = replaced

                    if quality == 100 or previous_over_quality is None:
                        break

                    for refine_quality in range(previous_over_quality - 1, quality, -1):
                        refined = temp_dir / f"candidate-q{refine_quality}.pdf"
                        replaced = _build_candidate(input_path, refined, quality=refine_quality)
                        _verify_candidate(input_path, refined)
                        refined_size = refined.stat().st_size
                        attempts.append(ImageFitAttempt(quality=refine_quality, size_bytes=refined_size))
                        if refined_size <= target_bytes:
                            best_candidate = refined
                            best_quality = refine_quality
                            best_size = refined_size
                            best_replaced = replaced
                            break
                    break

                previous_over_quality = quality

            if best_candidate is None or best_quality is None or best_size is None:
                return ImageFitResult(
                    status=ImageFitStatus.TARGET_NOT_MET,
                    input_path=str(input_path), output_path=None,
                    input_size_bytes=input_size, output_size_bytes=None,
                    target_bytes=target_bytes, selected_quality=None,
                    images_replaced=0, attempts=tuple(attempts),
                    reasons=(
                        f"target was not met at or above minimum JPEG quality {min_quality}",
                        "no output was written; later PoCs may add resolution reduction or another route",
                    ),
                )

            shutil.copyfile(best_candidate, output_path)
    except Exception:
        if output_path.exists():
            output_path.unlink()
        raise

    _verify_candidate(input_path, output_path)
    final_size = output_path.stat().st_size
    if final_size > target_bytes:
        output_path.unlink(missing_ok=True)
        raise RuntimeError("selected output unexpectedly exceeds target after final copy")

    return ImageFitResult(
        status=ImageFitStatus.FITTED,
        input_path=str(input_path), output_path=str(output_path),
        input_size_bytes=input_size, output_size_bytes=final_size,
        target_bytes=target_bytes, selected_quality=best_quality,
        images_replaced=best_replaced, attempts=tuple(attempts),
        reasons=(
            f"image-heavy route met target at JPEG quality {best_quality}",
            "each quality attempt was rebuilt from the original PDF",
            "page count, media boxes, and rotation were verified before accepting the output",
        ),
    )
