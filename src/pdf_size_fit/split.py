from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from math import isfinite
from pathlib import Path
import shutil
import tempfile
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, StreamObject

from .progress import (
    ProgressCallback,
    ProgressEvent,
    ProgressPhase,
    report_progress,
)


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
ALLOWED_PAGES_NODE_KEYS = frozenset(
    {
        "/Type",
        "/Parent",
        "/Kids",
        "/Count",
        "/Resources",
        "/MediaBox",
        "/CropBox",
        "/Rotate",
    }
)


class SplitEligibilityStatus(str, Enum):
    ELIGIBLE = "eligible"
    NOT_NEEDED = "not-needed"
    UNSUPPORTED_DOCUMENT = "unsupported-document"


class SplitStatus(str, Enum):
    SPLIT = "split"
    NOT_NEEDED = "not-needed"
    SINGLE_PAGE_OVERSIZE = "single-page-oversize"
    UNSUPPORTED_DOCUMENT = "unsupported-document"
    SPLIT_FAILED = "split-failed"


@dataclass(frozen=True)
class SourceSnapshot:
    size_bytes: int
    mtime_ns: int


@dataclass(frozen=True)
class SplitEligibilityResult:
    status: SplitEligibilityStatus
    input_path: str
    input_size_bytes: int
    target_bytes: int
    page_count: int
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


@dataclass(frozen=True)
class SplitPart:
    part_number: int
    page_start: int
    page_end: int
    output_path: str
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SplitResult:
    status: SplitStatus
    input_path: str
    input_size_bytes: int
    target_bytes: int
    page_count: int
    parts: tuple[SplitPart, ...]
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


@dataclass(frozen=True)
class _PageSpec:
    mediabox: tuple[float, float, float, float]
    rotation: int


class _PageTreeRefusal(Exception):
    pass


def capture_source_snapshot(path: str | Path) -> SourceSnapshot:
    stat = Path(path).stat()
    return SourceSnapshot(size_bytes=stat.st_size, mtime_ns=stat.st_mtime_ns)


def _require_source_snapshot(path: Path, expected: SourceSnapshot) -> None:
    current = capture_source_snapshot(path)
    if current != expected:
        raise RuntimeError("source PDF changed during the split operation")


def _resolve(obj: Any) -> Any:
    return obj.get_object() if isinstance(obj, IndirectObject) else obj


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
        return (
            "document metadata is not a readable stream, so PDF/A status "
            "cannot be checked safely"
        )
    try:
        data = metadata.get_data().lower()
    except Exception:
        return "document metadata cannot be decoded, so PDF/A status cannot be checked safely"
    if b"http://www.aiim.org/pdfa/ns/id/" in data or b"pdfaid:part" in data:
        return "PDF contains standard PDF/A identification metadata"
    return None


def _same_box(first: tuple[float, ...], second: tuple[float, ...]) -> bool:
    return all(a == b for a, b in zip(first, second))


_PageTreeIdentity = tuple[int, int, int]


def _page_tree_identity(
    reference: Any,
    reader: PdfReader,
    context: str,
) -> _PageTreeIdentity:
    if not isinstance(reference, IndirectObject) or reference.pdf is not reader:
        raise _PageTreeRefusal(
            f"{context} does not have a reliable source-object identity"
        )
    if (
        isinstance(reference.idnum, bool)
        or not isinstance(reference.idnum, int)
        or reference.idnum <= 0
        or isinstance(reference.generation, bool)
        or not isinstance(reference.generation, int)
        or reference.generation < 0
    ):
        raise _PageTreeRefusal(f"{context} has an invalid indirect-object identity")
    return (id(reference.pdf), reference.idnum, reference.generation)


def _raw_page_tree_refusal(reader: PdfReader, root: DictionaryObject) -> str | None:
    try:
        if "/Pages" not in root:
            raise _PageTreeRefusal("PDF catalog does not contain a raw /Pages reference")
        root_reference = root.raw_get("/Pages")
        root_identity = _page_tree_identity(
            root_reference,
            reader,
            "catalog /Pages root",
        )
        seen: set[_PageTreeIdentity] = set()
        raw_leaf_identities: list[_PageTreeIdentity] = []

        def visit(
            reference: Any,
            parent_identity: _PageTreeIdentity | None,
            *,
            is_root: bool,
        ) -> int:
            context = "catalog /Pages root" if is_root else "page-tree child"
            identity = _page_tree_identity(reference, reader, context)
            if identity in seen:
                raise _PageTreeRefusal(
                    "raw page tree repeats an object identity or contains a cycle"
                )
            seen.add(identity)

            node = _resolve(reference)
            if not isinstance(node, DictionaryObject):
                raise _PageTreeRefusal(f"{context} is not a readable dictionary")
            node_type = node.get("/Type")
            if node_type not in ("/Pages", "/Page"):
                raise _PageTreeRefusal(
                    f"{context} has missing or invalid /Type {node_type!r}"
                )
            if is_root and node_type != "/Pages":
                raise _PageTreeRefusal("catalog /Pages root is not /Type /Pages")

            if is_root:
                if "/Parent" in node:
                    raise _PageTreeRefusal(
                        "catalog /Pages root must not contain /Parent"
                    )
            else:
                if "/Parent" not in node:
                    raise _PageTreeRefusal(f"raw {node_type} child is missing /Parent")
                actual_parent = _page_tree_identity(
                    node.raw_get("/Parent"),
                    reader,
                    f"raw {node_type} child /Parent",
                )
                if actual_parent != parent_identity:
                    raise _PageTreeRefusal(
                        f"raw {node_type} child /Parent does not match traversal parent"
                    )

            if node_type == "/Page":
                unsupported_leaf_keys = sorted(
                    str(key) for key in node.keys() if key not in ALLOWED_PAGE_KEYS
                )
                if unsupported_leaf_keys:
                    raise _PageTreeRefusal(
                        "raw /Page leaf contains unsupported dictionary keys that "
                        "are not reconstructed: " + ", ".join(unsupported_leaf_keys)
                    )
                raw_leaf_identities.append(identity)
                return 1

            unsupported_node_keys = sorted(
                str(key) for key in node.keys() if key not in ALLOWED_PAGES_NODE_KEYS
            )
            if unsupported_node_keys:
                raise _PageTreeRefusal(
                    "raw /Pages node contains unsupported dictionary keys that "
                    "are not reconstructed: " + ", ".join(unsupported_node_keys)
                )
            if "/Kids" not in node:
                raise _PageTreeRefusal("raw /Pages node is missing /Kids")
            kids = _resolve(node.raw_get("/Kids"))
            if not isinstance(kids, (ArrayObject, list)):
                raise _PageTreeRefusal("raw /Pages /Kids is not a readable array")
            if "/Count" not in node:
                raise _PageTreeRefusal("raw /Pages node is missing /Count")
            count = _resolve(node.raw_get("/Count"))
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise _PageTreeRefusal(
                    "raw /Pages /Count is not a non-negative integer"
                )

            descendant_count = sum(
                visit(kid, identity, is_root=False) for kid in kids
            )
            if count != descendant_count:
                raise _PageTreeRefusal(
                    f"raw /Pages /Count {count} does not match discovered leaf "
                    f"count {descendant_count}"
                )
            return descendant_count

        visit(root_reference, None, is_root=True)

        try:
            flattened_pages = tuple(reader.pages)
        except Exception as exc:
            raise _PageTreeRefusal(
                "pypdf could not flatten the validated raw page tree reliably "
                f"({type(exc).__name__})"
            ) from exc
        flattened_identities = tuple(
            _page_tree_identity(
                page.indirect_reference,
                reader,
                f"flattened page {index}",
            )
            for index, page in enumerate(flattened_pages, start=1)
        )
        if flattened_identities != tuple(raw_leaf_identities):
            raise _PageTreeRefusal(
                "raw page-tree leaf order/count/identity disagrees with flattened pages"
            )
        if root_identity not in seen:
            raise _PageTreeRefusal("catalog /Pages root identity was not traversed")
    except _PageTreeRefusal as exc:
        return str(exc)
    except Exception as exc:
        return (
            "raw page tree could not be inspected reliably "
            f"({type(exc).__name__})"
        )
    return None


def _read_page_specs(
    reader: PdfReader,
) -> tuple[tuple[_PageSpec, ...] | None, str | None]:
    specs: list[_PageSpec] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            box = tuple(float(value) for value in page.mediabox)
        except Exception:
            return None, f"page {index} MediaBox cannot be read reliably"
        if len(box) != 4 or not all(isfinite(value) for value in box):
            return None, f"page {index} MediaBox is not a finite four-number rectangle"
        width = box[2] - box[0]
        height = box[3] - box[1]
        if width <= 0 or height <= 0:
            return None, f"page {index} MediaBox has non-positive dimensions"

        try:
            raw_rotation = float(page.get("/Rotate", 0) or 0)
        except Exception:
            return None, f"page {index} rotation cannot be read reliably"
        if (
            not isfinite(raw_rotation)
            or not raw_rotation.is_integer()
            or int(raw_rotation) % 90
        ):
            return (
                None,
                f"page {index} rotation is not an integer multiple of 90 degrees",
            )
        rotation = int(raw_rotation)

        try:
            cropbox = tuple(float(value) for value in page.cropbox)
        except Exception:
            return None, f"page {index} CropBox cannot be read reliably"
        if not _same_box(box, cropbox):
            return None, f"page {index} has a CropBox different from its MediaBox"

        if any(key in page for key in ("/BleedBox", "/TrimBox", "/ArtBox")):
            return (
                None,
                f"page {index} uses additional page boxes that are not preserved",
            )

        try:
            user_unit = float(page.get("/UserUnit", 1) or 1)
        except Exception:
            return None, f"page {index} UserUnit cannot be read reliably"
        if not isfinite(user_unit) or user_unit != 1.0:
            return None, f"page {index} uses unsupported UserUnit {user_unit!r}"

        annotations = _resolve(page.get("/Annots"))
        if isinstance(annotations, (ArrayObject, list)) and annotations:
            return None, f"page {index} contains annotations"
        if annotations is not None and not isinstance(annotations, (ArrayObject, list)):
            return None, f"page {index} annotations cannot be inspected safely"

        if "/AF" in page:
            return None, f"page {index} contains associated files"

        unsupported_page_keys = sorted(
            str(key) for key in page.keys() if key not in ALLOWED_PAGE_KEYS
        )
        if unsupported_page_keys:
            return None, (
                f"page {index} contains unsupported dictionary keys: "
                + ", ".join(unsupported_page_keys)
            )

        specs.append(_PageSpec(mediabox=box, rotation=rotation))

    return tuple(specs), None


def _preflight(reader: PdfReader) -> tuple[tuple[_PageSpec, ...] | None, str | None]:
    if reader.is_encrypted:
        return None, "encrypted PDFs are not supported for page splitting"

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

    if "/AcroForm" in root:
        return None, "PDF contains an AcroForm structure"

    names = _resolve(root.get("/Names"))
    if names is not None and not isinstance(names, DictionaryObject):
        return None, "document name tree cannot be inspected safely"
    if isinstance(names, DictionaryObject) and "/EmbeddedFiles" in names:
        return None, "PDF contains embedded files or file attachments"
    if isinstance(names, DictionaryObject) and names:
        return None, "PDF contains named document-level semantics"

    if "/AF" in root:
        return None, "PDF contains associated or embedded files"

    pdfa_reason = _pdfa_refusal(root)
    if pdfa_reason is not None:
        return None, pdfa_reason

    if "/Outlines" in root:
        return None, "PDF contains outlines/bookmarks"

    navigation_keys = (
        "/OpenAction",
        "/AA",
        "/Dests",
        "/PageLabels",
        "/Threads",
        "/StructTreeRoot",
        "/OCProperties",
        "/Collection",
    )
    present_navigation = [key for key in navigation_keys if key in root]
    if present_navigation:
        return None, (
            "PDF contains unsupported document-level semantics: "
            + ", ".join(present_navigation)
        )

    unsupported_catalog_keys = sorted(
        str(key) for key in root.keys() if key not in ALLOWED_CATALOG_KEYS
    )
    if unsupported_catalog_keys:
        return None, (
            "PDF catalog contains unsupported keys: "
            + ", ".join(unsupported_catalog_keys)
        )

    page_tree_reason = _raw_page_tree_refusal(reader, root)
    if page_tree_reason is not None:
        return None, page_tree_reason

    return _read_page_specs(reader)


def evaluate_split_eligibility(
    input_path: str | Path,
    *,
    target_bytes: int = 10_000_000,
) -> SplitEligibilityResult:
    if target_bytes <= 0:
        raise ValueError("target_bytes must be greater than zero")

    input_path = Path(input_path)
    input_size = input_path.stat().st_size
    reader = PdfReader(str(input_path))

    if reader.is_encrypted:
        return SplitEligibilityResult(
            status=SplitEligibilityStatus.UNSUPPORTED_DOCUMENT,
            input_path=str(input_path),
            input_size_bytes=input_size,
            target_bytes=target_bytes,
            page_count=0,
            reasons=("encrypted PDFs are not supported for page splitting",),
        )

    page_count = len(reader.pages)
    if input_size <= target_bytes:
        return SplitEligibilityResult(
            status=SplitEligibilityStatus.NOT_NEEDED,
            input_path=str(input_path),
            input_size_bytes=input_size,
            target_bytes=target_bytes,
            page_count=page_count,
            reasons=("input is already at or below the target size",),
        )

    if page_count < 2:
        return SplitEligibilityResult(
            status=SplitEligibilityStatus.UNSUPPORTED_DOCUMENT,
            input_path=str(input_path),
            input_size_bytes=input_size,
            target_bytes=target_bytes,
            page_count=page_count,
            reasons=("page splitting requires at least two source pages",),
        )

    page_specs, refusal = _preflight(reader)
    if refusal is not None or page_specs is None:
        return SplitEligibilityResult(
            status=SplitEligibilityStatus.UNSUPPORTED_DOCUMENT,
            input_path=str(input_path),
            input_size_bytes=input_size,
            target_bytes=target_bytes,
            page_count=page_count,
            reasons=(refusal or "split safety preflight failed closed",),
        )

    return SplitEligibilityResult(
        status=SplitEligibilityStatus.ELIGIBLE,
        input_path=str(input_path),
        input_size_bytes=input_size,
        target_bytes=target_bytes,
        page_count=len(page_specs),
        reasons=(
            "document passed the strict page-splitting safety preflight",
            "page splitting still requires explicit user approval",
        ),
    )


def _page_signature(
    reader: PdfReader,
    page_start: int,
    page_end: int,
) -> tuple[tuple[float, float, float, float, int], ...]:
    values: list[tuple[float, float, float, float, int]] = []
    for page in reader.pages[page_start - 1 : page_end]:
        box = tuple(float(value) for value in page.mediabox)
        values.append((*box, int(page.get("/Rotate", 0) or 0)))
    return tuple(values)


def _build_subset(
    input_path: Path,
    candidate_path: Path,
    page_start: int,
    page_end: int,
) -> None:
    reader = PdfReader(str(input_path))
    writer = PdfWriter()
    for page_index in range(page_start - 1, page_end):
        writer.add_page(reader.pages[page_index])
    with candidate_path.open("wb") as output:
        writer.write(output)


def _validate_subset(
    input_path: Path,
    candidate_path: Path,
    page_start: int,
    page_end: int,
) -> None:
    source = PdfReader(str(input_path))
    candidate = PdfReader(str(candidate_path))

    if candidate.is_encrypted:
        raise RuntimeError("split candidate unexpectedly reopened as encrypted")

    expected_count = page_end - page_start + 1
    if len(candidate.pages) != expected_count:
        raise RuntimeError("split candidate page count differs from selected source range")

    if _page_signature(source, page_start, page_end) != _page_signature(
        candidate, 1, len(candidate.pages)
    ):
        raise RuntimeError(
            "split candidate MediaBox dimensions or rotation differ from source range"
        )

    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(candidate_path))
    try:
        if len(pdf) != expected_count:
            raise RuntimeError("PDFium split candidate page count disagrees with pypdf")
        for index in range(len(pdf)):
            page = pdf[index]
            bitmap = None
            try:
                bitmap = page.render(scale=0.25)
            except Exception as exc:
                raise RuntimeError(
                    f"split candidate page {index + 1} failed PDFium rendering: {exc}"
                ) from exc
            finally:
                if bitmap is not None:
                    bitmap.close()
                page.close()
    finally:
        pdf.close()


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


def _output_paths(
    input_path: Path,
    output_directory: Path,
    part_count: int,
) -> tuple[Path, ...]:
    stem = input_path.stem
    group = 1
    while True:
        if group == 1:
            names = [
                output_directory / f"{stem}-part-{number}.pdf"
                for number in range(1, part_count + 1)
            ]
        else:
            names = [
                output_directory / f"{stem}-split-{group}-part-{number}.pdf"
                for number in range(1, part_count + 1)
            ]
        if all(
            not path.exists() and path.resolve() != input_path.resolve()
            for path in names
        ):
            return tuple(names)
        group += 1


def _split_result(
    status: SplitStatus,
    input_path: Path,
    *,
    input_size: int,
    target_bytes: int,
    page_count: int,
    reasons: tuple[str, ...],
    parts: tuple[SplitPart, ...] = (),
) -> SplitResult:
    return SplitResult(
        status=status,
        input_path=str(input_path),
        input_size_bytes=input_size,
        target_bytes=target_bytes,
        page_count=page_count,
        parts=parts,
        reasons=reasons,
    )


def split_pdf(
    input_path: str | Path,
    *,
    target_bytes: int = 10_000_000,
    output_directory: str | Path | None = None,
    progress_callback: ProgressCallback | None = None,
    expected_source_snapshot: SourceSnapshot | None = None,
) -> SplitResult:
    if target_bytes <= 0:
        raise ValueError("target_bytes must be greater than zero")

    input_path = Path(input_path)
    output_directory_path = (
        input_path.parent if output_directory is None else Path(output_directory)
    )
    if not output_directory_path.is_dir():
        raise ValueError("output_directory must already exist")

    if expected_source_snapshot is not None:
        _require_source_snapshot(input_path, expected_source_snapshot)

    operation_snapshot = capture_source_snapshot(input_path)
    eligibility = evaluate_split_eligibility(input_path, target_bytes=target_bytes)

    if eligibility.status is SplitEligibilityStatus.NOT_NEEDED:
        return _split_result(
            SplitStatus.NOT_NEEDED,
            input_path,
            input_size=eligibility.input_size_bytes,
            target_bytes=target_bytes,
            page_count=eligibility.page_count,
            reasons=eligibility.reasons,
        )

    if eligibility.status is not SplitEligibilityStatus.ELIGIBLE:
        return _split_result(
            SplitStatus.UNSUPPORTED_DOCUMENT,
            input_path,
            input_size=eligibility.input_size_bytes,
            target_bytes=target_bytes,
            page_count=eligibility.page_count,
            reasons=eligibility.reasons,
        )

    page_count = eligibility.page_count
    total_budget = page_count * (page_count + 1) // 2
    completed = 0
    created_outputs: list[Path] = []

    try:
        with tempfile.TemporaryDirectory(prefix="pdf-size-fit-split-") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            selected: list[tuple[int, int, Path, int]] = []
            page_start = 1

            while page_start <= page_count:
                selected_part: tuple[int, int, Path, int] | None = None
                for page_end in range(page_count, page_start - 1, -1):
                    _require_source_snapshot(input_path, operation_snapshot)
                    candidate = temp_dir / (
                        f"candidate-{page_start:05d}-{page_end:05d}.pdf"
                    )
                    _build_subset(input_path, candidate, page_start, page_end)
                    _validate_subset(input_path, candidate, page_start, page_end)
                    _require_source_snapshot(input_path, operation_snapshot)

                    size = candidate.stat().st_size
                    completed += 1
                    report_progress(
                        progress_callback,
                        ProgressEvent(
                            phase=ProgressPhase.SPLIT_SEARCH,
                            completed=completed,
                            total=total_budget,
                        ),
                    )

                    if size <= target_bytes:
                        selected_part = (page_start, page_end, candidate, size)
                        break

                if selected_part is None:
                    return _split_result(
                        SplitStatus.SINGLE_PAGE_OVERSIZE,
                        input_path,
                        input_size=eligibility.input_size_bytes,
                        target_bytes=target_bytes,
                        page_count=page_count,
                        reasons=(
                            f"source page {page_start} cannot be emitted within the target byte limit",
                            "no final split output was written",
                        ),
                    )

                selected.append(selected_part)
                page_start = selected_part[1] + 1

            _require_source_snapshot(input_path, operation_snapshot)
            destinations = _output_paths(
                input_path,
                output_directory_path,
                len(selected),
            )

            parts: list[SplitPart] = []
            try:
                for part_number, (selection, destination) in enumerate(
                    zip(selected, destinations, strict=True),
                    start=1,
                ):
                    page_start, page_end, candidate, measured_size = selection
                    if destination.exists():
                        raise FileExistsError(
                            f"split destination appeared before publication: {destination}"
                        )
                    _copy_exclusive(candidate, destination)
                    created_outputs.append(destination)
                    _validate_subset(input_path, destination, page_start, page_end)
                    final_size = destination.stat().st_size
                    if final_size != measured_size:
                        raise RuntimeError(
                            "published split part size differs from validated staged candidate"
                        )
                    if final_size > target_bytes:
                        raise RuntimeError(
                            "published split part unexpectedly exceeds target byte limit"
                        )
                    parts.append(
                        SplitPart(
                            part_number=part_number,
                            page_start=page_start,
                            page_end=page_end,
                            output_path=str(destination),
                            size_bytes=final_size,
                        )
                    )
                _require_source_snapshot(input_path, operation_snapshot)
            except OSError as exc:
                for created in created_outputs:
                    created.unlink(missing_ok=True)
                created_outputs.clear()
                return _split_result(
                    SplitStatus.SPLIT_FAILED,
                    input_path,
                    input_size=eligibility.input_size_bytes,
                    target_bytes=target_bytes,
                    page_count=page_count,
                    reasons=(
                        f"split output publication failed: {type(exc).__name__}: {exc}",
                        "all final files created by this operation were removed",
                    ),
                )
            except Exception:
                for created in created_outputs:
                    created.unlink(missing_ok=True)
                created_outputs.clear()
                raise

            return _split_result(
                SplitStatus.SPLIT,
                input_path,
                input_size=eligibility.input_size_bytes,
                target_bytes=target_bytes,
                page_count=page_count,
                parts=tuple(parts),
                reasons=(
                    f"split completed into {len(parts)} validated part(s)",
                    "each part is at or below the requested byte target",
                    "the source PDF was not modified",
                ),
            )
    except (KeyboardInterrupt, SystemExit):
        for created in created_outputs:
            created.unlink(missing_ok=True)
        raise
    except Exception:
        for created in created_outputs:
            created.unlink(missing_ok=True)
        raise
