from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)

import pdf_size_fit.split as split_module
from pdf_size_fit.progress import ProgressEvent, ProgressPhase
from pdf_size_fit.split import (
    SplitEligibilityStatus,
    SplitStatus,
    evaluate_split_eligibility,
    split_pdf,
)


def _write_blank_pdf(path: Path, pages: int = 3) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    with path.open("wb") as output:
        writer.write(output)


def _write_with_root_entry(path: Path, key: str, value: object) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_blank_page(width=612, height=792)
    writer._root_object[NameObject(key)] = value
    with path.open("wb") as output:
        writer.write(output)


def _selected_ranges(result: object) -> list[tuple[int, int]]:
    return [(part.page_start, part.page_end) for part in result.parts]


def test_split_eligibility_accepts_minimal_safe_multi_page_pdf(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    _write_blank_pdf(source, pages=3)

    result = evaluate_split_eligibility(source, target_bytes=500)

    assert result.status is SplitEligibilityStatus.ELIGIBLE
    assert result.page_count == 3
    assert result.target_bytes == 500


@pytest.mark.parametrize(
    ("key", "value", "reason_fragment"),
    [
        ("/Perms", DictionaryObject(), "signature"),
        ("/AcroForm", DictionaryObject(), "AcroForm"),
        ("/Outlines", DictionaryObject(), "outlines"),
        ("/OpenAction", DictionaryObject(), "document-level"),
        ("/AF", ArrayObject(), "associated"),
    ],
)
def test_split_eligibility_rejects_document_level_semantics(
    tmp_path: Path,
    key: str,
    value: object,
    reason_fragment: str,
) -> None:
    source = tmp_path / "source.pdf"
    _write_with_root_entry(source, key, value)

    result = evaluate_split_eligibility(source, target_bytes=100)

    assert result.status is SplitEligibilityStatus.UNSUPPORTED_DOCUMENT
    assert any(reason_fragment.lower() in reason.lower() for reason in result.reasons)


def test_split_eligibility_rejects_pdfa_identification(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_blank_page(width=612, height=792)
    metadata = DecodedStreamObject()
    metadata.set_data(
        b'<rdf:Description xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/" '
        b'pdfaid:part="2" />'
    )
    writer._root_object[NameObject("/Metadata")] = metadata
    with source.open("wb") as output:
        writer.write(output)

    result = evaluate_split_eligibility(source, target_bytes=100)

    assert result.status is SplitEligibilityStatus.UNSUPPORTED_DOCUMENT
    assert any("PDF/A" in reason for reason in result.reasons)


def test_split_eligibility_rejects_annotations(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_blank_page(width=612, height=792)
    writer.pages[0][NameObject("/Annots")] = ArrayObject([DictionaryObject()])
    with source.open("wb") as output:
        writer.write(output)

    result = evaluate_split_eligibility(source, target_bytes=100)

    assert result.status is SplitEligibilityStatus.UNSUPPORTED_DOCUMENT
    assert any("annotation" in reason.lower() for reason in result.reasons)


def test_split_pdf_preserves_source_and_validates_every_part(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    _write_blank_pdf(source, pages=3)
    before = source.read_bytes()

    result = split_pdf(source, target_bytes=500)

    assert result.status is SplitStatus.SPLIT
    assert source.read_bytes() == before
    assert len(result.parts) == 3
    for part in result.parts:
        path = Path(part.output_path)
        assert path.exists()
        assert path.stat().st_size == part.size_bytes
        assert part.size_bytes <= 500
        reopened = PdfReader(str(path))
        assert len(reopened.pages) == part.page_end - part.page_start + 1


def test_split_search_selects_largest_fitting_contiguous_ranges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.pdf"
    _write_blank_pdf(source, pages=5)

    sizes = {
        (1, 5): 800,
        (1, 4): 700,
        (1, 3): 400,
        (3, 5): 1100,
        (3, 4): 700,
    }
    built: list[tuple[int, int]] = []

    def fake_build_subset(
        input_path: Path,
        candidate_path: Path,
        page_start: int,
        page_end: int,
    ) -> None:
        built.append((page_start, page_end))
        size = sizes.get((page_start, page_end), 300)
        candidate_path.write_bytes(b"x" * size)

    monkeypatch.setattr(split_module, "_build_subset", fake_build_subset)
    monkeypatch.setattr(split_module, "_validate_subset", lambda *args, **kwargs: None)

    result = split_pdf(source, target_bytes=500)

    assert result.status is SplitStatus.SPLIT
    assert _selected_ranges(result) == [(1, 3), (4, 5)]
    assert built[:3] == [(1, 5), (1, 4), (1, 3)]
    assert built[3:5] == [(4, 5), (4, 4)] or built[3:4] == [(4, 5)]


def test_split_search_does_not_assume_size_monotonicity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.pdf"
    _write_blank_pdf(source, pages=4)

    sizes = {
        (1, 4): 800,
        (1, 3): 400,
        (4, 4): 300,
    }

    def fake_build_subset(
        input_path: Path,
        candidate_path: Path,
        page_start: int,
        page_end: int,
    ) -> None:
        candidate_path.write_bytes(b"x" * sizes.get((page_start, page_end), 800))

    monkeypatch.setattr(split_module, "_build_subset", fake_build_subset)
    monkeypatch.setattr(split_module, "_validate_subset", lambda *args, **kwargs: None)

    result = split_pdf(source, target_bytes=500)

    assert result.status is SplitStatus.SPLIT
    assert _selected_ranges(result) == [(1, 3), (4, 4)]


def test_single_page_oversize_is_explicit_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.pdf"
    _write_blank_pdf(source, pages=2)

    def fake_build_subset(
        input_path: Path,
        candidate_path: Path,
        page_start: int,
        page_end: int,
    ) -> None:
        candidate_path.write_bytes(b"x" * 1200)

    monkeypatch.setattr(split_module, "_build_subset", fake_build_subset)
    monkeypatch.setattr(split_module, "_validate_subset", lambda *args, **kwargs: None)

    result = split_pdf(source, target_bytes=500)

    assert result.status is SplitStatus.SINGLE_PAGE_OVERSIZE
    assert result.parts == ()
    assert not list(tmp_path.glob("*-part-*.pdf"))


def test_collision_uses_new_group_without_overwriting(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    _write_blank_pdf(source, pages=2)
    collision = tmp_path / "source-part-1.pdf"
    collision.write_bytes(b"keep-me")

    result = split_pdf(source, target_bytes=500)

    assert result.status is SplitStatus.SPLIT
    assert collision.read_bytes() == b"keep-me"
    assert all(Path(part.output_path).name.startswith("source-split-2-part-") for part in result.parts)


def test_publish_failure_rolls_back_final_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.pdf"
    _write_blank_pdf(source, pages=3)
    original_copy = split_module._copy_exclusive
    calls = 0

    def failing_copy(source_path: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic publication failure")
        original_copy(source_path, destination)

    monkeypatch.setattr(split_module, "_copy_exclusive", failing_copy)

    result = split_pdf(source, target_bytes=500)

    assert result.status is SplitStatus.SPLIT_FAILED
    assert result.parts == ()
    assert not list(tmp_path.glob("source-part-*.pdf"))


def test_split_progress_has_stable_total_and_monotonic_completed(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.pdf"
    _write_blank_pdf(source, pages=3)
    events: list[ProgressEvent] = []

    result = split_pdf(source, target_bytes=500, progress_callback=events.append)

    assert result.status is SplitStatus.SPLIT
    assert events
    assert {event.phase for event in events} == {ProgressPhase.SPLIT_SEARCH}
    assert {event.total for event in events} == {6}
    assert [event.completed for event in events] == list(range(1, len(events) + 1))
    assert len(events) <= 6


def test_progress_callback_exception_does_not_change_split_outcome(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.pdf"
    _write_blank_pdf(source, pages=2)

    def broken_callback(event: ProgressEvent) -> None:
        raise RuntimeError("progress is observational")

    result = split_pdf(source, target_bytes=500, progress_callback=broken_callback)

    assert result.status is SplitStatus.SPLIT
    assert len(result.parts) == 2


@pytest.mark.parametrize("exc_type", [KeyboardInterrupt, SystemExit])
def test_progress_process_control_exceptions_propagate(
    tmp_path: Path,
    exc_type: type[BaseException],
) -> None:
    source = tmp_path / "source.pdf"
    _write_blank_pdf(source, pages=2)

    def control_callback(event: ProgressEvent) -> None:
        raise exc_type()

    with pytest.raises(exc_type):
        split_pdf(source, target_bytes=500, progress_callback=control_callback)

    assert not list(tmp_path.glob("source-part-*.pdf"))
