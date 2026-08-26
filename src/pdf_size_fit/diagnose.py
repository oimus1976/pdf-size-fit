from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable

from pypdf import PdfReader
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, StreamObject


class Route(str, Enum):
    SKIP = "skip"
    IMAGE_HEAVY = "image-heavy"
    VECTOR_MONOCHROME = "vector-monochrome"
    VECTOR_COLOR = "vector-color"
    UNCLASSIFIED = "unclassified"


@dataclass(frozen=True)
class Diagnosis:
    path: str
    file_size_bytes: int
    target_bytes: int
    page_count: int
    image_stream_bytes: int
    vector_stream_bytes: int
    image_ratio: float
    vector_ratio: float
    rendered_color_fraction: float | None
    route: Route
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["route"] = self.route.value
        return data


def _resolve(obj: Any) -> Any:
    return obj.get_object() if isinstance(obj, IndirectObject) else obj


def _object_key(obj: Any) -> tuple[Any, ...]:
    if isinstance(obj, IndirectObject):
        return ("indirect", obj.idnum, obj.generation)
    return ("direct", id(obj))


def _raw_stream_size(stream: StreamObject) -> int:
    """Return encoded stream bytes when pypdf exposes them.

    pypdf does not currently expose a stable public API for encoded stream length.
    This PoC intentionally isolates the private `_data` access here so it can be
    replaced if the reader/writer stack changes.
    """
    raw = getattr(stream, "_data", None)
    if isinstance(raw, (bytes, bytearray)):
        return len(raw)

    # pypdf removes /Length from parsed StreamObject dictionaries, so /Length is
    # not a reliable fallback here. Use the documented serialization method if
    # the private storage detail is unavailable.
    buffer = BytesIO()
    try:
        stream.write_to_stream(buffer)
    except Exception:
        return 0

    serialized = buffer.getvalue()
    marker = b"\nstream\n"
    suffix = b"\nendstream"
    start = serialized.find(marker)
    if start < 0 or not serialized.endswith(suffix):
        return 0
    return len(serialized) - (start + len(marker)) - len(suffix)


def _iter_streams(value: Any) -> Iterable[tuple[Any, StreamObject]]:
    if value is None:
        return
    if isinstance(value, (list, ArrayObject)):
        for item in value:
            yield from _iter_streams(item)
        return
    key_source = value
    resolved = _resolve(value)
    if isinstance(resolved, StreamObject):
        yield key_source, resolved


def _collect_xobjects(resources: Any, seen: set[tuple[Any, ...]]) -> tuple[int, int]:
    """Return (image stream bytes, non-image Form stream bytes)."""
    resources = _resolve(resources)
    if not isinstance(resources, DictionaryObject):
        return 0, 0

    xobjects = _resolve(resources.get("/XObject"))
    if not isinstance(xobjects, DictionaryObject):
        return 0, 0

    image_bytes = 0
    form_bytes = 0

    for ref in xobjects.values():
        key = _object_key(ref)
        if key in seen:
            continue
        seen.add(key)

        obj = _resolve(ref)
        if not isinstance(obj, StreamObject):
            continue

        subtype = obj.get("/Subtype")
        if subtype == "/Image":
            image_bytes += _raw_stream_size(obj)
        elif subtype == "/Form":
            form_bytes += _raw_stream_size(obj)
            nested_images, nested_forms = _collect_xobjects(obj.get("/Resources"), seen)
            image_bytes += nested_images
            form_bytes += nested_forms

    return image_bytes, form_bytes


def _rendered_color_fraction(path: Path, dpi: int = 36) -> float:
    """Return the maximum per-page fraction of sampled non-white pixels with material chroma.

    All pages are scanned at low resolution. This intentionally biases classification
    toward the color route: a false color classification preserves color, while a false
    monochrome classification could destroy it during a later 1-bit conversion.
    """
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    max_page_fraction = 0.0
    try:
        for page_index in range(len(pdf)):
            page = pdf[page_index]
            try:
                image = page.render(scale=dpi / 72.0).to_pil().convert("RGB")
                pixels = image.load()
                width, height = image.size
                step = max(1, min(width, height) // 120)
                colored = 0
                considered = 0
                for y in range(0, height, step):
                    for x in range(0, width, step):
                        r, g, b = pixels[x, y]
                        if r > 248 and g > 248 and b > 248:
                            continue
                        considered += 1
                        if max(r, g, b) - min(r, g, b) >= 18:
                            colored += 1
                page_fraction = (colored / considered) if considered else 0.0
                max_page_fraction = max(max_page_fraction, page_fraction)
            finally:
                page.close()
    finally:
        pdf.close()

    return max_page_fraction


def diagnose_pdf(
    path: str | Path,
    *,
    target_bytes: int = 10_000_000,
    image_heavy_ratio: float = 0.60,
    vector_heavy_ratio: float = 0.35,
    color_fraction_threshold: float = 0.01,
) -> Diagnosis:
    if target_bytes <= 0:
        raise ValueError("target_bytes must be greater than zero")
    for name, value in (
        ("image_heavy_ratio", image_heavy_ratio),
        ("vector_heavy_ratio", vector_heavy_ratio),
        ("color_fraction_threshold", color_fraction_threshold),
    ):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be between 0.0 and 1.0")

    path = Path(path)
    file_size = path.stat().st_size
    reader = PdfReader(str(path))
    page_count = len(reader.pages)

    if file_size <= target_bytes:
        return Diagnosis(
            path=str(path), file_size_bytes=file_size, target_bytes=target_bytes,
            page_count=page_count, image_stream_bytes=0, vector_stream_bytes=0,
            image_ratio=0.0, vector_ratio=0.0, rendered_color_fraction=None,
            route=Route.SKIP,
            reasons=(f"file size {file_size} bytes is already at or below target {target_bytes} bytes",),
        )

    seen: set[tuple[Any, ...]] = set()
    image_bytes = 0
    vector_bytes = 0

    for page in reader.pages:
        raw_contents = page.get("/Contents")
        for ref, stream in _iter_streams(raw_contents):
            key = _object_key(ref)
            if key not in seen:
                seen.add(key)
                vector_bytes += _raw_stream_size(stream)

        nested_images, form_bytes = _collect_xobjects(page.get("/Resources"), seen)
        image_bytes += nested_images
        vector_bytes += form_bytes

    image_ratio = image_bytes / file_size if file_size else 0.0
    vector_ratio = vector_bytes / file_size if file_size else 0.0

    if image_ratio >= image_heavy_ratio:
        return Diagnosis(
            path=str(path), file_size_bytes=file_size, target_bytes=target_bytes,
            page_count=page_count, image_stream_bytes=image_bytes, vector_stream_bytes=vector_bytes,
            image_ratio=image_ratio, vector_ratio=vector_ratio, rendered_color_fraction=None,
            route=Route.IMAGE_HEAVY,
            reasons=(
                f"encoded image streams account for about {image_ratio:.1%} of the PDF file size",
                "image recompression is the least-destructive first route",
            ),
        )

    if vector_ratio >= vector_heavy_ratio and image_ratio < image_heavy_ratio:
        color_fraction = _rendered_color_fraction(path)
        if color_fraction >= color_fraction_threshold:
            route = Route.VECTOR_COLOR
            color_reason = (
                "at least one rendered page shows material color use "
                f"(maximum sampled page fraction {color_fraction:.1%})"
            )
        else:
            route = Route.VECTOR_MONOCHROME
            color_reason = (
                "all rendered pages are effectively monochrome at the current sampling threshold "
                f"(maximum sampled page fraction {color_fraction:.1%} colored)"
            )

        return Diagnosis(
            path=str(path), file_size_bytes=file_size, target_bytes=target_bytes,
            page_count=page_count, image_stream_bytes=image_bytes, vector_stream_bytes=vector_bytes,
            image_ratio=image_ratio, vector_ratio=vector_ratio, rendered_color_fraction=color_fraction,
            route=route,
            reasons=(
                f"page/form content streams account for about {vector_ratio:.1%} of the PDF file size",
                f"encoded image streams account for only about {image_ratio:.1%}",
                color_reason,
            ),
        )

    return Diagnosis(
        path=str(path), file_size_bytes=file_size, target_bytes=target_bytes,
        page_count=page_count, image_stream_bytes=image_bytes, vector_stream_bytes=vector_bytes,
        image_ratio=image_ratio, vector_ratio=vector_ratio, rendered_color_fraction=None,
        route=Route.UNCLASSIFIED,
        reasons=(
            "no size contributor crossed the current routing thresholds",
            f"image ratio={image_ratio:.1%}, vector/content ratio={vector_ratio:.1%}",
            "PoC fails closed instead of guessing a destructive compression route",
        ),
    )
