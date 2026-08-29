from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from io import BytesIO
from math import ceil, isfinite
from pathlib import Path
import shutil
import tempfile
from typing import Any

from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    DecodedStreamObject,
    DictionaryObject,
    IndirectObject,
    NameObject,
    NumberObject,
    RectangleObject,
    StreamObject,
)

from .diagnose import Route, diagnose_pdf


FIXED_DPI = 300
PREFLIGHT_DPI = 72
MIDTONE_MIN = 33
MIDTONE_MAX = 246
MAX_MIDTONE_FRACTION = 0.01
ALLOWED_CATALOG_KEYS = frozenset({"/Type", "/Pages"})
ALLOWED_PAGE_KEYS = frozenset(
    {
        "/Type",
        "/Parent",
        "/Resources",
        "/MediaBox",
        "/CropBox",
        "/Contents",
        "/Rotate",
        "/UserUnit",
        "/Annots",
    }
)


class MonochromeFitStatus(str, Enum):
    FITTED = "fitted"
    SKIP = "skip"
    ROUTE_MISMATCH = "route-mismatch"
    UNSUPPORTED_DOCUMENT = "unsupported-document"
    TARGET_NOT_MET = "target-not-met"


@dataclass(frozen=True)
class MonochromeFitResult:
    status: MonochromeFitStatus
    input_path: str
    output_path: str | None
    input_size_bytes: int
    output_size_bytes: int | None
    target_bytes: int
    route: str
    dpi: int
    bits_per_pixel: int
    compression: str
    page_count: int
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


@dataclass(frozen=True)
class _PageSpec:
    mediabox: tuple[float, float, float, float]
    rotation: int

    @property
    def width(self) -> float:
        return self.mediabox[2] - self.mediabox[0]

    @property
    def height(self) -> float:
        return self.mediabox[3] - self.mediabox[1]


def _resolve(obj: Any) -> Any:
    return obj.get_object() if isinstance(obj, IndirectObject) else obj


def _result(
    status: MonochromeFitStatus,
    input_path: Path,
    *,
    input_size: int,
    target_bytes: int,
    page_count: int,
    reasons: tuple[str, ...],
    output_path: Path | None = None,
    output_size: int | None = None,
) -> MonochromeFitResult:
    return MonochromeFitResult(
        status=status,
        input_path=str(input_path),
        output_path=str(output_path) if output_path is not None else None,
        input_size_bytes=input_size,
        output_size_bytes=output_size,
        target_bytes=target_bytes,
        route=Route.VECTOR_MONOCHROME.value,
        dpi=FIXED_DPI,
        bits_per_pixel=1,
        compression="CCITT Group 4",
        page_count=page_count,
        reasons=reasons,
    )


def _contains_signature_field(field: Any, inherited_ft: Any = None) -> bool:
    field = _resolve(field)
    if not isinstance(field, DictionaryObject):
        return False
    field_type = field.get("/FT", inherited_ft)
    if field_type == "/Sig":
        return True
    kids = _resolve(field.get("/Kids"))
    if isinstance(kids, (ArrayObject, list)):
        return any(_contains_signature_field(kid, field_type) for kid in kids)
    return False


def _pdfa_refusal(root: DictionaryObject) -> str | None:
    metadata = _resolve(root.get("/Metadata"))
    if metadata is None:
        return None
    if not isinstance(metadata, StreamObject):
        return "document metadata is not a readable stream, so PDF/A status cannot be checked safely"
    try:
        data = metadata.get_data().lower()
    except Exception:
        return "document metadata cannot be decoded, so PDF/A status cannot be checked safely"
    if b"http://www.aiim.org/pdfa/ns/id/" in data or b"pdfaid:part" in data:
        return "PDF contains standard PDF/A identification metadata"
    return None


def _same_box(first: tuple[float, ...], second: tuple[float, ...]) -> bool:
    return all(a == b for a, b in zip(first, second))


def _read_page_specs(reader: PdfReader) -> tuple[tuple[_PageSpec, ...] | None, str | None]:
    specs: list[_PageSpec] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            box = tuple(float(value) for value in page.mediabox)
        except Exception:
            return None, f"page {index} MediaBox cannot be read reliably"
        if len(box) != 4 or not all(isfinite(value) for value in box):
            return None, f"page {index} MediaBox is not a finite four-number rectangle"
        spec = _PageSpec(box, 0)
        if spec.width <= 0 or spec.height <= 0:
            return None, f"page {index} MediaBox has non-positive dimensions"

        try:
            raw_rotation = float(page.get("/Rotate", 0) or 0)
        except Exception:
            return None, f"page {index} rotation cannot be read reliably"
        if not isfinite(raw_rotation) or not raw_rotation.is_integer() or int(raw_rotation) % 90:
            return None, f"page {index} rotation is not an integer multiple of 90 degrees"
        rotation = int(raw_rotation)

        try:
            cropbox = tuple(float(value) for value in page.cropbox)
        except Exception:
            return None, f"page {index} CropBox cannot be read reliably"
        if not _same_box(box, cropbox):
            return None, f"page {index} has a CropBox different from its MediaBox"

        if any(key in page for key in ("/BleedBox", "/TrimBox", "/ArtBox")):
            return None, f"page {index} uses additional page boxes that are not preserved"
        try:
            user_unit = float(page.get("/UserUnit", 1) or 1)
        except Exception:
            return None, f"page {index} UserUnit cannot be read reliably"
        if not isfinite(user_unit) or user_unit != 1.0:
            return None, f"page {index} uses unsupported UserUnit {user_unit!r}"
        annotations = _resolve(page.get("/Annots"))
        if isinstance(annotations, (ArrayObject, list)) and annotations:
            return None, f"page {index} contains annotations that whole-page rasterization would discard"
        if annotations is not None and not isinstance(annotations, (ArrayObject, list)):
            return None, f"page {index} annotations cannot be inspected safely"
        if "/AF" in page:
            return None, f"page {index} contains associated files"

        unsupported_page_keys = sorted(
            str(key) for key in page.keys() if key not in ALLOWED_PAGE_KEYS
        )
        if unsupported_page_keys:
            return None, (
                f"page {index} contains unsupported dictionary keys that are not "
                "reconstructed: " + ", ".join(unsupported_page_keys)
            )

        specs.append(_PageSpec(box, rotation))
    return tuple(specs), None


def _preflight(reader: PdfReader) -> tuple[tuple[_PageSpec, ...] | None, str | None]:
    if reader.is_encrypted:
        return None, "encrypted PDFs are not supported by the destructive monochrome route"

    root = _resolve(reader.trailer.get("/Root"))
    if not isinstance(root, DictionaryObject):
        return None, "PDF catalog cannot be read reliably"

    acroform = _resolve(root.get("/AcroForm"))
    fields: Any = None
    if acroform is not None and not isinstance(acroform, DictionaryObject):
        return None, "AcroForm structure cannot be inspected safely"
    if isinstance(acroform, DictionaryObject):
        fields = _resolve(acroform.get("/Fields"))
        if fields is not None and not isinstance(fields, (ArrayObject, list)):
            return None, "AcroForm fields cannot be inspected safely"

    if "/Perms" in root or (
        isinstance(fields, (ArrayObject, list))
        and any(_contains_signature_field(field) for field in fields)
    ):
        return None, "PDF contains a signature field or certification-permissions structure"
    if isinstance(fields, (ArrayObject, list)) and fields:
        return None, "PDF contains AcroForm fields that whole-page rasterization would discard"
    if "/AcroForm" in root:
        return None, "PDF contains an AcroForm structure that is not preserved"

    names = _resolve(root.get("/Names"))
    if names is not None and not isinstance(names, DictionaryObject):
        return None, "document name tree cannot be inspected safely"
    if isinstance(names, DictionaryObject) and "/EmbeddedFiles" in names:
        return None, "PDF contains embedded files or file attachments"
    if "/AF" in root:
        return None, "PDF contains associated or embedded files"

    pdfa_reason = _pdfa_refusal(root)
    if pdfa_reason is not None:
        return None, pdfa_reason

    if "/Outlines" in root:
        return None, "PDF contains outlines/bookmarks that are not preserved"
    navigation_keys = (
        "/OpenAction", "/AA", "/Dests", "/PageLabels", "/Threads",
        "/StructTreeRoot", "/OCProperties", "/Collection",
    )
    present_navigation = [key for key in navigation_keys if key in root]
    if present_navigation:
        return None, (
            "PDF contains unsupported document-level semantics: "
            + ", ".join(present_navigation)
        )
    if isinstance(names, DictionaryObject) and names:
        return None, "PDF contains named document-level semantics that are not preserved"

    unsupported_catalog_keys = sorted(
        str(key) for key in root.keys() if key not in ALLOWED_CATALOG_KEYS
    )
    if unsupported_catalog_keys:
        return None, (
            "PDF catalog contains unsupported keys that are not reconstructed: "
            + ", ".join(unsupported_catalog_keys)
        )

    return _read_page_specs(reader)


def _bilevel_suitability_refusal(
    input_path: Path,
    page_specs: tuple[_PageSpec, ...],
) -> str | None:
    try:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(input_path))
        try:
            if len(pdf) != len(page_specs):
                raise RuntimeError("PDFium and pypdf disagree on the source page count")
            for index, spec in enumerate(page_specs, start=1):
                source_page = pdf[index - 1]
                bitmap = None
                grayscale = None
                try:
                    normalized_rotation = spec.rotation % 360
                    if source_page.get_rotation() != normalized_rotation:
                        raise RuntimeError(
                            f"page {index} rotation differs between PDF readers"
                        )
                    bitmap = source_page.render(
                        scale=PREFLIGHT_DPI / 72.0,
                        rotation=(-normalized_rotation) % 360,
                        grayscale=True,
                        draw_annots=False,
                    )
                    grayscale = bitmap.to_pil().convert("L")
                    expected_size = (
                        ceil(spec.width * PREFLIGHT_DPI / 72.0),
                        ceil(spec.height * PREFLIGHT_DPI / 72.0),
                    )
                    if grayscale.size != expected_size:
                        raise RuntimeError(
                            f"page {index} rendered at {grayscale.size}, expected "
                            f"{expected_size} at {PREFLIGHT_DPI} dpi"
                        )
                    histogram = grayscale.histogram()
                    total_pixels = grayscale.width * grayscale.height
                    if len(histogram) != 256 or total_pixels <= 0:
                        raise RuntimeError(
                            f"page {index} did not produce a valid 8-bit grayscale image"
                        )
                    midtone_pixels = sum(histogram[MIDTONE_MIN : MIDTONE_MAX + 1])
                    midtone_fraction = midtone_pixels / total_pixels
                    if midtone_fraction > MAX_MIDTONE_FRACTION:
                        return (
                            f"page {index} contains material grayscale/midtone content "
                            f"({midtone_fraction:.3%} of pixels at luminance "
                            f"{MIDTONE_MIN}..{MIDTONE_MAX}, above the "
                            f"{MAX_MIDTONE_FRACTION:.1%} limit)"
                        )
                finally:
                    if grayscale is not None:
                        grayscale.close()
                    if bitmap is not None:
                        bitmap.close()
                    source_page.close()
        finally:
            pdf.close()
    except Exception as exc:
        return (
            "72 dpi bilevel-suitability rendering or inspection could not be "
            f"completed reliably ({type(exc).__name__})"
        )
    return None


def _destructive_content_refusal(
    input_path: Path,
    reader: PdfReader,
    page_specs: tuple[_PageSpec, ...],
) -> str | None:
    for index, page in enumerate(reader.pages, start=1):
        try:
            extracted_text = page.extract_text()
        except Exception as exc:
            return (
                f"page {index} extractable text could not be inspected reliably "
                f"({type(exc).__name__})"
            )
        if not isinstance(extracted_text, str):
            return (
                f"page {index} extractable text did not return a reliable string result"
            )
        if extracted_text.strip():
            return (
                f"page {index} contains selectable/searchable text that whole-page "
                "rasterization would discard"
            )

    return _bilevel_suitability_refusal(input_path, page_specs)


def _single_ccitt_image(image: Image.Image, writer: PdfWriter) -> IndirectObject:
    buffer = BytesIO()
    image.save(buffer, format="PDF", resolution=float(FIXED_DPI))
    buffer.seek(0)
    image_reader = PdfReader(buffer)
    images = image_reader.pages[0].images
    if len(images) != 1:
        raise RuntimeError("Pillow did not produce exactly one image XObject")
    ref = images[0].indirect_reference
    if ref is None:
        raise RuntimeError("Pillow produced an inline image instead of an image XObject")
    image_object = ref.get_object()

    filters = _resolve(image_object.get("/Filter"))
    if isinstance(filters, (ArrayObject, list)):
        filter_names = tuple(str(value) for value in filters)
    else:
        filter_names = (str(filters),)
    if filter_names != ("/CCITTFaxDecode",):
        raise RuntimeError("CCITT Group 4 encoding is unavailable in this Pillow build")
    if image_object.get("/BitsPerComponent") != 1 or image_object.get("/ColorSpace") != "/DeviceGray":
        raise RuntimeError("Pillow did not produce a 1-bit grayscale image XObject")

    decode_params = _resolve(image_object.get("/DecodeParms"))
    if isinstance(decode_params, (ArrayObject, list)) and len(decode_params) == 1:
        decode_params = _resolve(decode_params[0])
    if not isinstance(decode_params, DictionaryObject):
        raise RuntimeError("CCITT image is missing decode parameters")
    if (
        decode_params.get("/K") != -1
        or decode_params.get("/BlackIs1") != BooleanObject(True)
        or decode_params.get("/Columns") != image.width
        or decode_params.get("/Rows") != image.height
    ):
        raise RuntimeError("CCITT image does not use the required Group 4 decode parameters")

    cloned = image_object.clone(writer, force_duplicate=True)
    cloned_ref = getattr(cloned, "indirect_reference", None)
    if not isinstance(cloned_ref, IndirectObject):
        raise RuntimeError("CCITT image could not be attached to the output writer")
    return cloned_ref


def _number(value: float) -> bytes:
    return format(value, ".12g").encode("ascii")


def _build_candidate(
    input_path: Path,
    candidate_path: Path,
    page_specs: tuple[_PageSpec, ...],
) -> None:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(input_path))
    writer = PdfWriter()
    scale = FIXED_DPI / 72.0
    try:
        if len(pdf) != len(page_specs):
            raise RuntimeError("PDFium and pypdf disagree on the source page count")
        for index, spec in enumerate(page_specs):
            source_page = pdf[index]
            bitmap = None
            try:
                normalized_rotation = spec.rotation % 360
                if source_page.get_rotation() != normalized_rotation:
                    raise RuntimeError(f"page {index + 1} rotation differs between PDF readers")
                bitmap = source_page.render(
                    scale=scale,
                    rotation=(-normalized_rotation) % 360,
                    grayscale=True,
                    draw_annots=False,
                )
                monochrome = bitmap.to_pil().convert("1")
            finally:
                if bitmap is not None:
                    bitmap.close()
                source_page.close()

            expected_size = (ceil(spec.width * scale), ceil(spec.height * scale))
            if monochrome.size != expected_size:
                raise RuntimeError(
                    f"page {index + 1} rendered at {monochrome.size}, expected {expected_size} at 300 dpi"
                )

            image_ref = _single_ccitt_image(monochrome, writer)
            page = writer.add_blank_page(width=spec.width, height=spec.height)
            page[NameObject("/MediaBox")] = RectangleObject(spec.mediabox)
            page[NameObject("/Rotate")] = NumberObject(spec.rotation)
            page[NameObject("/Resources")] = DictionaryObject(
                {
                    NameObject("/XObject"): DictionaryObject(
                        {NameObject("/Im0"): image_ref}
                    )
                }
            )
            left, bottom, _, _ = spec.mediabox
            content = DecodedStreamObject()
            content.set_data(
                b"q\n"
                + _number(spec.width) + b" 0 0 " + _number(spec.height) + b" "
                + _number(left) + b" " + _number(bottom) + b" cm\n"
                + b"/Im0 Do\nQ\n"
            )
            page.replace_contents(content)
    finally:
        pdf.close()

    with candidate_path.open("wb") as output:
        writer.write(output)


def _page_signature(reader: PdfReader) -> tuple[tuple[float, float, float, float, int], ...]:
    signature = []
    for page in reader.pages:
        box = tuple(float(value) for value in page.mediabox)
        signature.append((*box, int(page.get("/Rotate", 0) or 0)))
    return tuple(signature)


def _verify_candidate(input_path: Path, candidate_path: Path) -> None:
    source = PdfReader(str(input_path))
    candidate = PdfReader(str(candidate_path))
    if candidate.is_encrypted:
        raise RuntimeError("candidate unexpectedly reopened as encrypted")
    if len(source.pages) != len(candidate.pages):
        raise RuntimeError("candidate page count differs from input")
    if _page_signature(source) != _page_signature(candidate):
        raise RuntimeError("candidate MediaBox dimensions or rotation differ from input")
    for index, page in enumerate(candidate.pages, start=1):
        images = page.images
        if len(images) != 1:
            raise RuntimeError(f"candidate page {index} does not contain exactly one image")
        image_object = images[0].indirect_reference.get_object()
        filters = _resolve(image_object.get("/Filter"))
        if isinstance(filters, (ArrayObject, list)):
            filters = tuple(str(value) for value in filters)
        else:
            filters = (str(filters),)
        decode_params = _resolve(image_object.get("/DecodeParms"))
        if isinstance(decode_params, (ArrayObject, list)) and len(decode_params) == 1:
            decode_params = _resolve(decode_params[0])
        if (
            filters != ("/CCITTFaxDecode",)
            or image_object.get("/BitsPerComponent") != 1
            or image_object.get("/ColorSpace") != "/DeviceGray"
            or not isinstance(decode_params, DictionaryObject)
            or decode_params.get("/K") != -1
            or decode_params.get("/BlackIs1") != BooleanObject(True)
        ):
            raise RuntimeError(f"candidate page {index} is not 1-bit CCITT Group 4")


def _copy_exclusive(source: Path, destination: Path) -> None:
    created = False
    try:
        with source.open("rb") as input_file, destination.open("xb") as output_file:
            created = True
            shutil.copyfileobj(input_file, output_file)
    except Exception:
        if created:
            destination.unlink(missing_ok=True)
        raise


def fit_monochrome_vector_pdf(
    input_path: str | Path,
    output_path: str | Path,
    *,
    target_bytes: int = 10_000_000,
    dpi: int = FIXED_DPI,
) -> MonochromeFitResult:
    if target_bytes <= 0:
        raise ValueError("target_bytes must be greater than zero")
    if dpi != FIXED_DPI:
        raise ValueError("dpi must be exactly 300; DPI search is not validated")

    input_path = Path(input_path)
    output_path = Path(output_path)
    if input_path.resolve() == output_path.resolve():
        raise ValueError("output_path must differ from input_path")
    if output_path.exists():
        raise FileExistsError(f"output path already exists: {output_path}")

    input_size = input_path.stat().st_size
    if input_size <= target_bytes:
        reader = PdfReader(str(input_path))
        return _result(
            MonochromeFitStatus.SKIP,
            input_path,
            input_size=input_size,
            target_bytes=target_bytes,
            page_count=0 if reader.is_encrypted else len(reader.pages),
            reasons=("input is already at or below the target size; no output was written",),
        )

    reader = PdfReader(str(input_path))
    page_specs, refusal = _preflight(reader)
    if refusal is not None or page_specs is None:
        return _result(
            MonochromeFitStatus.UNSUPPORTED_DOCUMENT,
            input_path,
            input_size=input_size,
            target_bytes=target_bytes,
            page_count=0 if reader.is_encrypted else len(reader.pages),
            reasons=(refusal or "document failed the destructive-rasterization safety gate",),
        )

    refusal = _destructive_content_refusal(input_path, reader, page_specs)
    if refusal is not None:
        return _result(
            MonochromeFitStatus.UNSUPPORTED_DOCUMENT,
            input_path,
            input_size=input_size,
            target_bytes=target_bytes,
            page_count=len(page_specs),
            reasons=(refusal, "no output was written"),
        )

    diagnosis = diagnose_pdf(input_path, target_bytes=target_bytes)
    if diagnosis.route is not Route.VECTOR_MONOCHROME:
        return _result(
            MonochromeFitStatus.ROUTE_MISMATCH,
            input_path,
            input_size=input_size,
            target_bytes=target_bytes,
            page_count=len(page_specs),
            reasons=(
                f"diagnosis proposed route {diagnosis.route.value!r}, not 'vector-monochrome'",
                "no output was written",
            ),
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_created = False
    try:
        with tempfile.TemporaryDirectory(prefix="pdf-size-fit-monochrome-") as temp_dir:
            candidate = Path(temp_dir) / "candidate-300dpi-g4.pdf"
            _build_candidate(input_path, candidate, page_specs)
            _verify_candidate(input_path, candidate)
            candidate_size = candidate.stat().st_size
            if candidate_size > target_bytes:
                return _result(
                    MonochromeFitStatus.TARGET_NOT_MET,
                    input_path,
                    input_size=input_size,
                    target_bytes=target_bytes,
                    page_count=len(page_specs),
                    reasons=(
                        f"fixed 300 dpi candidate is {candidate_size} bytes, above target {target_bytes} bytes",
                        "DPI was not reduced or searched; no output was written",
                    ),
                )
            _copy_exclusive(candidate, output_path)
            output_created = True
        _verify_candidate(input_path, output_path)
        output_size = output_path.stat().st_size
        if output_size > target_bytes:
            raise RuntimeError("accepted output unexpectedly exceeds target after final copy")
    except Exception:
        if output_created:
            output_path.unlink(missing_ok=True)
        raise

    return _result(
        MonochromeFitStatus.FITTED,
        input_path,
        input_size=input_size,
        target_bytes=target_bytes,
        page_count=len(page_specs),
        output_path=output_path,
        output_size=output_size,
        reasons=(
            "diagnosis selected the vector-monochrome route for the requested target",
            "all pages were rendered by PDFium at fixed 300 dpi and encoded as 1-bit CCITT Group 4",
            "page count, MediaBox dimensions, rotation, reader reopenability, encoding, and target size were verified",
            "whole-page rasterization is destructive and does not preserve selectable text or vector scalability",
        ),
    )
