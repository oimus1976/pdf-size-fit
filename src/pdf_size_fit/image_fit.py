from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from math import ceil
from pathlib import Path
import shutil
import tempfile
from typing import Any

from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, NameObject, StreamObject

from .diagnose import Route, diagnose_pdf


class ImageFitStatus(str, Enum):
    FITTED = "fitted"
    ALREADY_BELOW_TARGET = "already-below-target"
    ROUTE_MISMATCH = "route-mismatch"
    UNSUPPORTED_IMAGE = "unsupported-image"
    TARGET_NOT_MET = "target-not-met"
    SIGNED_PDF_UNSUPPORTED = "signed-pdf-unsupported"
    PDF_A_UNSUPPORTED = "pdf-a-unsupported"


@dataclass(frozen=True)
class ImageFitAttempt:
    quality: int
    size_bytes: int
    scale: float = 1.0


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
    selected_scale: float | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


class UnsupportedImageError(RuntimeError):
    pass


_REPLACED_IMAGE_KEYS = {
    "/Type", "/Subtype", "/Width", "/Height", "/ColorSpace",
    "/BitsPerComponent", "/Filter", "/DecodeParms", "/Length",
}
_PRESERVED_IMAGE_KEYS = {
    "/SMask", "/Interpolate", "/Intent", "/Name", "/StructParent",
    "/ID", "/OPI", "/Metadata", "/OC",
}
_REJECTED_IMAGE_KEYS = {"/Decode", "/Mask", "/ImageMask", "/SMaskInData"}


def _resolve_pdf_obj(obj: Any) -> Any:
    return obj.get_object() if isinstance(obj, IndirectObject) else obj


def _contains_signature_field(field: Any, inherited_ft: Any = None) -> bool:
    field = _resolve_pdf_obj(field)
    if not isinstance(field, DictionaryObject):
        return False
    field_type = field.get("/FT", inherited_ft)
    if field_type == "/Sig":
        return True
    kids = _resolve_pdf_obj(field.get("/Kids"))
    if isinstance(kids, (ArrayObject, list)):
        return any(_contains_signature_field(kid, field_type) for kid in kids)
    return False


def _has_signature_structure(reader: PdfReader) -> bool:
    root = _resolve_pdf_obj(reader.trailer.get("/Root"))
    if not isinstance(root, DictionaryObject):
        return False
    if "/Perms" in root:
        return True
    acroform = _resolve_pdf_obj(root.get("/AcroForm"))
    if not isinstance(acroform, DictionaryObject):
        return False
    fields = _resolve_pdf_obj(acroform.get("/Fields"))
    if not isinstance(fields, (ArrayObject, list)):
        return False
    return any(_contains_signature_field(field) for field in fields)


def _has_pdfa_marker(reader: PdfReader) -> bool:
    root = _resolve_pdf_obj(reader.trailer.get("/Root"))
    if not isinstance(root, DictionaryObject):
        return False
    metadata = _resolve_pdf_obj(root.get("/Metadata"))
    if not isinstance(metadata, StreamObject):
        return False
    try:
        data = metadata.get_data().lower()
    except Exception:
        return False
    return b"http://www.aiim.org/pdfa/ns/id/" in data or b"pdfaid:part" in data


def _ref_key(ref: IndirectObject) -> tuple[int, int]:
    return ref.idnum, ref.generation


def _simple_colorspace(obj: StreamObject) -> str | None:
    colorspace = obj.get("/ColorSpace")
    if isinstance(colorspace, IndirectObject):
        colorspace = colorspace.get_object()
    if colorspace in ("/DeviceRGB", "/DeviceGray"):
        return str(colorspace)
    return None


def _validate_image_for_replacement(img: Any) -> tuple[IndirectObject, dict[Any, Any]]:
    ref = img.indirect_reference
    if ref is None:
        raise UnsupportedImageError("inline images cannot be replaced with pypdf ImageFile.replace()")

    obj = ref.get_object()
    if not isinstance(obj, StreamObject) or obj.get("/Subtype") != "/Image":
        raise UnsupportedImageError("encountered an image entry that is not an image XObject stream")

    keys = {str(key) for key in obj.keys()}
    rejected = keys & _REJECTED_IMAGE_KEYS
    if rejected:
        raise UnsupportedImageError(
            "unsupported image dictionary keys that may change rendering semantics: "
            + ", ".join(sorted(rejected))
        )
    unknown = keys - _REPLACED_IMAGE_KEYS - _PRESERVED_IMAGE_KEYS - _REJECTED_IMAGE_KEYS
    if unknown:
        raise UnsupportedImageError(
            "unknown image dictionary keys are not safe to discard during replacement: "
            + ", ".join(sorted(unknown))
        )

    if _simple_colorspace(obj) is None:
        raise UnsupportedImageError(f"unsupported image color space: {obj.get('/ColorSpace')!r}")

    if obj.get("/BitsPerComponent") != 8:
        raise UnsupportedImageError(
            f"unsupported bits per component: {obj.get('/BitsPerComponent')!r}; current PoC accepts 8-bit images"
        )

    smask = obj.get("/SMask")
    if smask is not None:
        smask_obj = smask.get_object() if isinstance(smask, IndirectObject) else smask
        if not isinstance(smask_obj, StreamObject):
            raise UnsupportedImageError("/SMask is not a stream")
        if smask_obj.get("/Width") != obj.get("/Width") or smask_obj.get("/Height") != obj.get("/Height"):
            raise UnsupportedImageError("/SMask dimensions do not match the base image")

    if img.image is None:
        raise UnsupportedImageError("pypdf could not decode an image XObject through Pillow")

    preserved = {key: value for key, value in obj.items() if str(key) in _PRESERVED_IMAGE_KEYS}
    return ref, preserved


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


def _build_candidate(input_path: Path, output_path: Path, *, quality: int, scale: float = 1.0) -> int:
    if not 0.0 < scale <= 1.0:
        raise ValueError("scale must be greater than 0 and at most 1")

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

            ref, preserved = _validate_image_for_replacement(img)
            has_smask = NameObject("/SMask") in preserved
            replacement = _base_image_for_jpeg(img.image, has_smask=has_smask)

            if scale < 1.0:
                if has_smask:
                    raise UnsupportedImageError(
                        "downsampling an image with /SMask is not supported until the soft mask can be resized in lockstep"
                    )
                new_width = max(1, round(replacement.width * scale))
                new_height = max(1, round(replacement.height * scale))
                replacement = replacement.resize((new_width, new_height), Image.Resampling.LANCZOS)

            try:
                img.replace(replacement, quality=quality, subsampling=0)
            except Exception as exc:
                raise UnsupportedImageError(
                    f"image replacement failed for {img.name}: {type(exc).__name__}: {exc}"
                ) from exc

            new_obj = ref.get_object()
            for key, value in preserved.items():
                new_obj[key] = value

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
    min_scale: float = 0.50,
) -> ImageFitResult:
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

    if _has_signature_structure(PdfReader(str(input_path))):
        return ImageFitResult(
            status=ImageFitStatus.SIGNED_PDF_UNSUPPORTED,
            input_path=str(input_path), output_path=None,
            input_size_bytes=input_size, output_size_bytes=None,
            target_bytes=target_bytes, selected_quality=None,
            images_replaced=0, attempts=(),
            reasons=(
                "PDF contains a signature field or certification permissions structure",
                "rewriting a signed PDF can invalidate signatures, so the current PoC writes no output",
            ),
        )

    if _has_pdfa_marker(PdfReader(str(input_path))):
        return ImageFitResult(
            status=ImageFitStatus.PDF_A_UNSUPPORTED,
            input_path=str(input_path), output_path=None,
            input_size_bytes=input_size, output_size_bytes=None,
            target_bytes=target_bytes, selected_quality=None,
            images_replaced=0, attempts=(),
            reasons=(
                "PDF contains PDF/A identification metadata",
                "the current PoC does not verify PDF/A conformance after rewriting, so no output is written",
            ),
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    attempts: list[ImageFitAttempt] = []
    best_candidate: Path | None = None
    best_quality: int | None = None
    best_size: int | None = None
    best_replaced = 0
    best_scale: float | None = None

    try:
        with tempfile.TemporaryDirectory(prefix="pdf-size-fit-") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            cache: dict[tuple[int, int], tuple[Path, int, int]] = {}

            def measure(scale_percent: int, quality: int) -> tuple[Path, int, int]:
                cache_key = (scale_percent, quality)
                cached = cache.get(cache_key)
                if cached is not None:
                    return cached

                scale = scale_percent / 100.0
                candidate = temp_dir / f"candidate-s{scale_percent:03d}-q{quality}.pdf"
                replaced = _build_candidate(input_path, candidate, quality=quality, scale=scale)
                _verify_candidate(input_path, candidate)
                size = candidate.stat().st_size
                attempts.append(ImageFitAttempt(quality=quality, size_bytes=size, scale=scale))
                result = (candidate, size, replaced)
                cache[cache_key] = result
                return result

            def search_quality(scale_percent: int) -> tuple[Path, int, int, int] | None:
                previous_over_quality: int | None = None
                for quality in _quality_probes(min_quality):
                    candidate, size, replaced = measure(scale_percent, quality)
                    if size <= target_bytes:
                        best = (candidate, quality, size, replaced)
                        if quality == 100 or previous_over_quality is None:
                            return best

                        for refine_quality in range(previous_over_quality - 1, quality, -1):
                            refined, refined_size, refined_replaced = measure(scale_percent, refine_quality)
                            if refined_size <= target_bytes:
                                return refined, refine_quality, refined_size, refined_replaced
                        return best
                    previous_over_quality = quality
                return None

            try:
                full_resolution = search_quality(100)
            except UnsupportedImageError as exc:
                return ImageFitResult(
                    status=ImageFitStatus.UNSUPPORTED_IMAGE,
                    input_path=str(input_path), output_path=None,
                    input_size_bytes=input_size, output_size_bytes=None,
                    target_bytes=target_bytes, selected_quality=None,
                    images_replaced=0, attempts=tuple(attempts),
                    reasons=(str(exc), "input was left unchanged and no output was written"),
                )

            if full_resolution is not None:
                best_candidate, best_quality, best_size, best_replaced = full_resolution
                best_scale = 1.0
            elif min_scale < 1.0:
                min_percent = max(1, ceil(min_scale * 100))
                if min_percent <= 99:
                    try:
                        _, min_size, _ = measure(min_percent, min_quality)
                    except UnsupportedImageError as exc:
                        return ImageFitResult(
                            status=ImageFitStatus.UNSUPPORTED_IMAGE,
                            input_path=str(input_path), output_path=None,
                            input_size_bytes=input_size, output_size_bytes=None,
                            target_bytes=target_bytes, selected_quality=None,
                            images_replaced=0, attempts=tuple(attempts),
                            reasons=(
                                str(exc),
                                "full-resolution JPEG quality search did not meet the target and the downsampling fallback is unsafe for this image structure",
                                "input was left unchanged and no output was written",
                            ),
                        )

                    if min_size <= target_bytes:
                        low = min_percent
                        high = 99
                        while low < high:
                            mid = (low + high + 1) // 2
                            _, mid_size, _ = measure(mid, min_quality)
                            if mid_size <= target_bytes:
                                low = mid
                            else:
                                high = mid - 1

                        selected_percent = low
                        downsampled = search_quality(selected_percent)
                        if downsampled is None:
                            raise RuntimeError("minimum-quality scale probe fit but quality search found no fitting candidate")
                        best_candidate, best_quality, best_size, best_replaced = downsampled
                        best_scale = selected_percent / 100.0

            if best_candidate is None or best_quality is None or best_size is None or best_scale is None:
                return ImageFitResult(
                    status=ImageFitStatus.TARGET_NOT_MET,
                    input_path=str(input_path), output_path=None,
                    input_size_bytes=input_size, output_size_bytes=None,
                    target_bytes=target_bytes, selected_quality=None,
                    images_replaced=0, attempts=tuple(attempts),
                    reasons=(
                        f"target was not met at or above JPEG quality {min_quality} and image scale {min_scale:.0%}",
                        "no output was written; another compression route or user-visible fallback is required",
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

    if best_scale < 1.0:
        fit_reason = (
            f"image-heavy route met target at {best_scale:.0%} image scale and JPEG quality {best_quality}"
        )
    else:
        fit_reason = f"image-heavy route met target at full image resolution and JPEG quality {best_quality}"

    return ImageFitResult(
        status=ImageFitStatus.FITTED,
        input_path=str(input_path), output_path=str(output_path),
        input_size_bytes=input_size, output_size_bytes=final_size,
        target_bytes=target_bytes, selected_quality=best_quality,
        images_replaced=best_replaced, attempts=tuple(attempts),
        reasons=(
            fit_reason,
            "each candidate was rebuilt from the original PDF; lossy recompression was not cumulative",
            "page count, media boxes, and rotation were verified before accepting the output",
        ),
        selected_scale=best_scale,
    )
