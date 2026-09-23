from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    RectangleObject,
    TextStringObject,
)

import pdf_size_fit.color_fit as color_fit
from pdf_size_fit.diagnose import Diagnosis, Route
from pdf_size_fit.color_fit import (
    ColorFitStatus,
    fit_color_vector_pdf,
)
from pdf_size_fit.progress import ProgressEvent, ProgressPhase


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _generate_vector_pdf(
    path: Path,
    *,
    color: bool = False,
    page_specs: tuple[tuple[float, float, int], ...] = ((595.0, 842.0, 0),),
    repeats: int = 8_000,
) -> None:
    writer = PdfWriter()
    stroke = b"0.8 0.1 0.1 RG\n" if color else b"0 G\n"
    drawing = stroke + b"0.5 w\n" + (b"40 40 m 540 790 l S\n" * repeats)
    for width, height, rotation in page_specs:
        page = writer.add_blank_page(width=width, height=height)
        page[NameObject("/Rotate")] = NumberObject(rotation)
        stream = DecodedStreamObject()
        stream.set_data(drawing)
        page.replace_contents(stream)
    with path.open("wb") as output:
        writer.write(output)


def _generate_text_pdf(path: Path, text: str) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): writer._add_object(font)}
            )
        }
    )
    stream = DecodedStreamObject()
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream.set_data(f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("ascii"))
    page.replace_contents(stream)
    with path.open("wb") as output:
        writer.write(output)


def _escape_pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _generate_vector_text_pdf(
    path: Path,
    pages: tuple[tuple[str, ...], ...],
    color: bool = True,
    repeats: int = 1,
) -> None:
    writer = PdfWriter()
    stroke = b"0.8 0.1 0.1 RG\n" if color else b"0 G\n"
    for text_lines in pages:
        page = writer.add_blank_page(width=595.0, height=842.0)
        drawing = []
        for line in text_lines:
            drawing.append(b"40 40 m 540 790 l S\n" * repeats)
            drawing.append(
                b"BT /F1 12 Tf 100 100 Td (" + line.encode("latin-1") + b") Tj ET\n"
            )
        stream = DecodedStreamObject()
        stream.set_data(stroke + b"0.5 w\n" + b"".join(drawing))
        page.replace_contents(stream)
    with path.open("wb") as output:
        writer.write(output)


def _generate_gray_vector_pdf(path: Path) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    stream = DecodedStreamObject()
    stream.set_data(b"0.5 g 0 0 595 842 re f")
    page.replace_contents(stream)
    with path.open("wb") as output:
        writer.write(output)


def _generate_chroma_vector_pdf(path: Path, *, thin: bool) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    drawing = b"0 G\n0.5 w\n" + (b"40 40 m 540 790 l S\n" * 8_000)
    if thin:
        drawing += b"1 0 0 rg 100 100 0.5 12 re f\n"
    else:
        drawing += b"0 0 1 rg 100 100 100 100 re f\n"
    stream = DecodedStreamObject()
    stream.set_data(drawing)
    page.replace_contents(stream)
    with path.open("wb") as output:
        writer.write(output)


def _non_pdfa_metadata() -> DecodedStreamObject:
    metadata = DecodedStreamObject()
    metadata.set_data(b"<metadata>synthetic non-PDF/A metadata</metadata>")
    return metadata


def _rewrite(source: Path, destination: Path, mutate) -> None:
    writer = PdfWriter(clone_from=str(source))
    mutate(writer)
    with destination.open("wb") as output:
        writer.write(output)


def _raw_writer_pages_root(
    writer: PdfWriter,
) -> tuple[object, DictionaryObject]:
    root_reference = writer.root_object.raw_get("/Pages")
    root = root_reference.get_object()
    assert isinstance(root, DictionaryObject)
    return root_reference, root


def _add_nested_pages_node(
    writer: PdfWriter,
    *,
    custom_key: str | None = None,
) -> None:
    root_reference, root = _raw_writer_pages_root(writer)
    kids = root.raw_get("/Kids")
    assert isinstance(kids, ArrayObject) and len(kids) == 1
    leaf_reference = kids[0]
    nested = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Pages"),
            NameObject("/Parent"): root_reference,
            NameObject("/Kids"): ArrayObject([leaf_reference]),
            NameObject("/Count"): NumberObject(1),
        }
    )
    if custom_key is not None:
        nested[NameObject(custom_key)] = NumberObject(1)
    nested_reference = writer._add_object(nested)
    leaf = leaf_reference.get_object()
    assert isinstance(leaf, DictionaryObject)
    leaf[NameObject("/Parent")] = nested_reference
    root[NameObject("/Kids")] = ArrayObject([nested_reference])
    root[NameObject("/Count")] = NumberObject(1)


def _fit_target(source: Path) -> int:
    return source.stat().st_size - 1


def _force_vector_color_diagnosis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def routed_diagnosis(
        path: str | Path,
        *,
        target_bytes: int = 10_000_000,
    ) -> Diagnosis:
        source = Path(path)
        return Diagnosis(
            path=str(source),
            file_size_bytes=source.stat().st_size,
            target_bytes=target_bytes,
            page_count=len(PdfReader(str(source)).pages),
            image_stream_bytes=0,
            vector_stream_bytes=0,
            image_ratio=0.0,
            vector_ratio=0.0,
            rendered_color_fraction=0.0,
            route=Route.VECTOR_COLOR,
            reasons=("synthetic vector-monochrome route precondition",),
        )

    monkeypatch.setattr(color_fit, "diagnose_pdf", routed_diagnosis)


def test_successful_fixed_300_dpi_color_fit_is_1bit_ccitt_g4(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "output.pdf"
    _generate_vector_pdf(source, color=True)
    before_hash = _sha256(source)

    result = fit_color_vector_pdf(source, output, target_bytes=_fit_target(source))

    assert result.status is ColorFitStatus.FITTED
    assert result.dpi == 200
    assert result.jpeg_quality == 90
    assert result.output_size_bytes is not None
    assert result.output_size_bytes <= result.target_bytes
    assert output.exists()
    assert _sha256(source) == before_hash

    image = PdfReader(str(output)).pages[0].images[0]
    image_object = image.indirect_reference.get_object()
    filters = image_object["/Filter"]
    assert filters == "/DCTDecode"
    assert image_object["/BitsPerComponent"] == 8


def test_fit_refuses_to_overwrite_source_or_existing_output(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "existing.pdf"
    _generate_vector_pdf(source, color=True)
    output.write_bytes(b"keep me")

    with pytest.raises(ValueError, match="must differ"):
        fit_color_vector_pdf(source, source, target_bytes=_fit_target(source))
    with pytest.raises(FileExistsError, match="already exists"):
        fit_color_vector_pdf(source, output, target_bytes=_fit_target(source))

    assert output.read_bytes() == b"keep me"


def test_fit_skips_input_already_below_target(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_pdf(source, repeats=10)

    result = fit_color_vector_pdf(
        source,
        output,
        target_bytes=source.stat().st_size,
    )

    assert result.status is ColorFitStatus.SKIP
    assert not output.exists()


def test_fit_requires_existing_vector_color_diagnosis(tmp_path: Path) -> None:
    source = tmp_path / "color.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_pdf(source, color=False)

    result = fit_color_vector_pdf(source, output, target_bytes=_fit_target(source))

    assert result.status is ColorFitStatus.ROUTE_MISMATCH
    assert "vector-color" in result.reasons[0]
    assert not output.exists()


def test_fit_refuses_non_whitespace_extractable_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "extractable-text.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_text_pdf(source, "private-marker-xyz")
    _force_vector_color_diagnosis(monkeypatch)

    result = fit_color_vector_pdf(source, output, target_bytes=1)

    assert result.status is ColorFitStatus.UNSUPPORTED_DOCUMENT
    assert "selectable/searchable text" in result.reasons[0]
    assert "private-marker-xyz" not in result.reasons[0]
    assert not output.exists()


def test_text_opt_in_fits_small_repeated_searchable_layer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "small-searchable-layer.pdf"
    output = tmp_path / "output.pdf"
    _generate_vector_text_pdf(
        source, (("12345678",), ("12345678",)), color=True, repeats=8000
    )
    _force_vector_color_diagnosis(monkeypatch)

    result = fit_color_vector_pdf(
        source,
        output,
        target_bytes=_fit_target(source),
        allow_small_searchable_text_rasterization=True,
    )

    assert result.status is ColorFitStatus.FITTED
    assert any("explicit opt-in" in reason for reason in result.reasons)
    assert any("both parsers" in reason for reason in result.reasons)
    assert any("search/copy semantics were lost" in reason for reason in result.reasons)
    assert output.exists()


def test_text_opt_in_refuses_more_than_eight_chars_on_one_page(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "too-many-page-characters.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_text_pdf(source, (("123456789",),), repeats=1)
    _force_vector_color_diagnosis(monkeypatch)
    monkeypatch.setattr(
        color_fit,
        "_pdfium_text_metrics",
        lambda *_args: (((0, 0),), None),
    )

    result = fit_color_vector_pdf(
        source,
        output,
        target_bytes=1,
        allow_small_searchable_text_rasterization=True,
    )

    assert result.status is ColorFitStatus.UNSUPPORTED_DOCUMENT
    assert "page 1 pypdf" in result.reasons[0]
    assert "9 non-whitespace" in result.reasons[0]
    assert "limit of 8" in result.reasons[0]
    assert not output.exists()


def test_text_opt_in_refuses_more_than_one_non_empty_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "too-many-lines.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_text_pdf(source, (("a", "b"),), repeats=1)
    _force_vector_color_diagnosis(monkeypatch)
    monkeypatch.setattr(
        color_fit,
        "_pdfium_text_metrics",
        lambda *_args: (((2, 2),), None),
    )
    monkeypatch.setattr(
        color_fit,
        "_pypdf_text_metrics",
        lambda *_args: (((2, 2),), None),
    )

    result = fit_color_vector_pdf(
        source,
        output,
        target_bytes=1,
        allow_small_searchable_text_rasterization=True,
    )

    assert result.status is ColorFitStatus.UNSUPPORTED_DOCUMENT
    assert "page 1 pypdf" in result.reasons[0]
    assert "2 non-empty lines" in result.reasons[0]
    assert "limit of 1" in result.reasons[0]
    assert not output.exists()


def test_text_opt_in_refuses_more_than_256_document_chars(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "too-many-document-characters.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_text_pdf(source, (("12345678",),) * 33, repeats=1)
    _force_vector_color_diagnosis(monkeypatch)
    monkeypatch.setattr(
        color_fit,
        "_pdfium_text_metrics",
        lambda *_args: (((0, 0),) * 33, None),
    )

    result = fit_color_vector_pdf(
        source,
        output,
        target_bytes=1,
        allow_small_searchable_text_rasterization=True,
    )

    assert result.status is ColorFitStatus.UNSUPPORTED_DOCUMENT
    assert "document pypdf" in result.reasons[0]
    assert "264 non-whitespace" in result.reasons[0]
    assert "limit of 256" in result.reasons[0]
    assert not output.exists()


def test_text_opt_in_refuses_pdfium_per_page_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_pdf(source, color=True)
    monkeypatch.setattr(
        color_fit,
        "_pdfium_text_metrics",
        lambda *_args: (((9, 1),), None),
    )

    result = fit_color_vector_pdf(
        source,
        output,
        target_bytes=1,
        allow_small_searchable_text_rasterization=True,
    )

    assert result.status is ColorFitStatus.UNSUPPORTED_DOCUMENT
    assert "page 1 PDFium" in result.reasons[0]
    assert "9 non-whitespace" in result.reasons[0]
    assert not output.exists()


def test_text_opt_in_refuses_pdfium_document_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_text_pdf(source, ((),) * 33, repeats=1)
    _force_vector_color_diagnosis(monkeypatch)
    monkeypatch.setattr(
        color_fit,
        "_pdfium_text_metrics",
        lambda *_args: (((8, 1),) * 33, None),
    )

    result = fit_color_vector_pdf(
        source,
        output,
        target_bytes=1,
        allow_small_searchable_text_rasterization=True,
    )

    assert result.status is ColorFitStatus.UNSUPPORTED_DOCUMENT
    assert "document PDFium" in result.reasons[0]
    assert "264 non-whitespace" in result.reasons[0]
    assert not output.exists()


def test_text_opt_in_refuses_parser_metric_disagreement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_pdf(source, color=True)
    monkeypatch.setattr(
        color_fit,
        "_pdfium_text_metrics",
        lambda *_args: (((1, 1),), None),
    )

    result = fit_color_vector_pdf(
        source,
        output,
        target_bytes=1,
        allow_small_searchable_text_rasterization=True,
    )

    assert result.status is ColorFitStatus.UNSUPPORTED_DOCUMENT
    assert "normalized text metrics disagree" in result.reasons[0]
    assert not output.exists()


def test_default_refuses_text_detected_only_by_pdfium(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_pdf(source, color=True)
    monkeypatch.setattr(
        color_fit,
        "_pdfium_text_metrics",
        lambda *_args: (((1, 1),), None),
    )

    result = fit_color_vector_pdf(source, output, target_bytes=1)

    assert result.status is ColorFitStatus.UNSUPPORTED_DOCUMENT
    assert "selectable/searchable text" in result.reasons[0]
    assert not output.exists()


def test_text_extraction_failure_fails_closed_with_opt_in(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_pdf(source, color=True)
    page_type = type(PdfReader(str(source)).pages[0])

    def fail_extraction(_page, *args, **kwargs):
        raise RuntimeError("synthetic extraction failure")

    monkeypatch.setattr(page_type, "extract_text", fail_extraction)
    result = fit_color_vector_pdf(
        source,
        output,
        target_bytes=1,
        allow_small_searchable_text_rasterization=True,
    )

    assert result.status is ColorFitStatus.UNSUPPORTED_DOCUMENT
    assert "pypdf text inspection could not be completed reliably" in result.reasons[0]
    assert not output.exists()


def test_non_string_text_extraction_result_fails_closed_with_opt_in(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_pdf(source, color=True)
    page_type = type(PdfReader(str(source)).pages[0])
    monkeypatch.setattr(page_type, "extract_text", lambda *_args, **_kwargs: None)

    result = fit_color_vector_pdf(
        source,
        output,
        target_bytes=1,
        allow_small_searchable_text_rasterization=True,
    )

    assert result.status is ColorFitStatus.UNSUPPORTED_DOCUMENT
    assert "did not return a reliable string" in result.reasons[0]
    assert not output.exists()


def test_pdfium_text_inspection_failure_fails_closed_with_opt_in(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_pdf(source, color=True)
    monkeypatch.setattr(
        color_fit,
        "_pdfium_text_metrics",
        lambda *_args: (
            None,
            "PDFium text inspection could not be completed reliably (RuntimeError)",
        ),
    )

    result = fit_color_vector_pdf(
        source,
        output,
        target_bytes=1,
        allow_small_searchable_text_rasterization=True,
    )

    assert result.status is ColorFitStatus.UNSUPPORTED_DOCUMENT
    assert "PDFium text inspection" in result.reasons[0]
    assert not output.exists()


def test_whitespace_extractable_text_does_not_by_itself_refuse(tmp_path: Path) -> None:
    source = tmp_path / "whitespace-text.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_text_pdf(source, "   ")

    result = fit_color_vector_pdf(source, output, target_bytes=1)

    assert "extractable text" not in result.reasons[0]
    assert result.status is not ColorFitStatus.UNSUPPORTED_DOCUMENT
    assert not output.exists()


def test_target_not_met_does_not_search_dpi_or_write_output(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_pdf(source, color=True)

    result = fit_color_vector_pdf(source, output, target_bytes=1)

    assert result.status is ColorFitStatus.TARGET_NOT_MET
    assert result.dpi == 200
    assert "DPI was not reduced or searched" in result.reasons[1]
    assert not output.exists()


def test_non_200_dpi_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "output.pdf"
    _generate_vector_pdf(source, color=True)

    with pytest.raises(ValueError, match="exactly 200"):
        fit_color_vector_pdf(source, output, dpi=299)


def test_page_count_size_and_rotation_are_preserved(tmp_path: Path) -> None:
    source = tmp_path / "mixed-pages.pdf"
    output = tmp_path / "output.pdf"
    _generate_vector_pdf(
        source,
        color=True,
        page_specs=((595.0, 842.0, 0), (420.0, 595.0, 90)),
    )
    source_reader = PdfReader(str(source))

    result = fit_color_vector_pdf(source, output, target_bytes=_fit_target(source))

    assert result.status is ColorFitStatus.FITTED
    output_reader = PdfReader(str(output))
    assert len(output_reader.pages) == len(source_reader.pages) == 2
    assert [tuple(float(v) for v in p.mediabox) for p in output_reader.pages] == [
        tuple(float(v) for v in p.mediabox) for p in source_reader.pages
    ]
    assert [int(p.get("/Rotate", 0)) for p in output_reader.pages] == [0, 90]


def test_raw_page_tree_refuses_unknown_root_pages_key(tmp_path: Path) -> None:
    base = tmp_path / "base.pdf"
    source = tmp_path / "custom-root-pages.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_pdf(base)

    def mutate(writer: PdfWriter) -> None:
        _, root = _raw_writer_pages_root(writer)
        root[NameObject("/CustomPagesSemantics")] = NumberObject(1)

    _rewrite(base, source, mutate)
    result = fit_color_vector_pdf(source, output, target_bytes=1)

    assert result.status is ColorFitStatus.UNSUPPORTED_DOCUMENT
    assert "/CustomPagesSemantics" in result.reasons[0]
    assert not output.exists()


def test_raw_page_tree_refuses_unknown_nested_pages_key(tmp_path: Path) -> None:
    base = tmp_path / "base.pdf"
    source = tmp_path / "custom-nested-pages.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_pdf(base)
    _rewrite(
        base,
        source,
        lambda writer: _add_nested_pages_node(
            writer,
            custom_key="/CustomPagesSemantics",
        ),
    )

    result = fit_color_vector_pdf(source, output, target_bytes=1)

    assert result.status is ColorFitStatus.UNSUPPORTED_DOCUMENT
    assert "/CustomPagesSemantics" in result.reasons[0]
    assert not output.exists()


def test_raw_page_tree_refuses_count_mismatch(tmp_path: Path) -> None:
    base = tmp_path / "base.pdf"
    source = tmp_path / "bad-count.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_pdf(base)

    def mutate(writer: PdfWriter) -> None:
        _, root = _raw_writer_pages_root(writer)
        root[NameObject("/Count")] = NumberObject(2)

    _rewrite(base, source, mutate)
    result = fit_color_vector_pdf(source, output, target_bytes=1)

    assert result.status is ColorFitStatus.UNSUPPORTED_DOCUMENT
    assert "/Count" in result.reasons[0]
    assert "discovered leaf count" in result.reasons[0]
    assert not output.exists()


def test_raw_page_tree_refuses_parent_mismatch(tmp_path: Path) -> None:
    base = tmp_path / "base.pdf"
    source = tmp_path / "bad-parent.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_pdf(base)

    def mutate(writer: PdfWriter) -> None:
        _, root = _raw_writer_pages_root(writer)
        kids = root.raw_get("/Kids")
        assert isinstance(kids, ArrayObject) and len(kids) == 1
        leaf = kids[0].get_object()
        wrong_parent = writer._add_object(
            DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Pages"),
                    NameObject("/Kids"): ArrayObject(),
                    NameObject("/Count"): NumberObject(0),
                }
            )
        )
        leaf[NameObject("/Parent")] = wrong_parent

    _rewrite(base, source, mutate)
    result = fit_color_vector_pdf(source, output, target_bytes=1)

    assert result.status is ColorFitStatus.UNSUPPORTED_DOCUMENT
    assert "/Parent does not match" in result.reasons[0]
    assert not output.exists()


@pytest.mark.parametrize("malformation", ["duplicate-leaf", "repeated-node", "cycle"])
def test_raw_page_tree_refuses_repeated_identity_or_cycle(
    tmp_path: Path,
    malformation: str,
) -> None:
    base = tmp_path / "base.pdf"
    source = tmp_path / f"{malformation}.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_pdf(base)

    def mutate(writer: PdfWriter) -> None:
        root_reference, root = _raw_writer_pages_root(writer)
        if malformation == "repeated-node":
            _add_nested_pages_node(writer)
            _, root = _raw_writer_pages_root(writer)
        kids = root.raw_get("/Kids")
        assert isinstance(kids, ArrayObject) and len(kids) == 1
        repeated_reference = root_reference if malformation == "cycle" else kids[0]
        kids.append(repeated_reference)
        root[NameObject("/Count")] = NumberObject(2)

    _rewrite(base, source, mutate)
    result = fit_color_vector_pdf(source, output, target_bytes=1)

    assert result.status is ColorFitStatus.UNSUPPORTED_DOCUMENT
    assert "repeats an object identity or contains a cycle" in result.reasons[0]
    assert not output.exists()


@pytest.mark.parametrize("node_type", [None, "/Invalid"])
def test_raw_page_tree_refuses_missing_or_invalid_type(
    tmp_path: Path,
    node_type: str | None,
) -> None:
    base = tmp_path / "base.pdf"
    source = tmp_path / "bad-type.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_pdf(base)

    def mutate(writer: PdfWriter) -> None:
        _, root = _raw_writer_pages_root(writer)
        if node_type is None:
            del root[NameObject("/Type")]
        else:
            root[NameObject("/Type")] = NameObject(node_type)

    _rewrite(base, source, mutate)
    result = fit_color_vector_pdf(source, output, target_bytes=1)

    assert result.status is ColorFitStatus.UNSUPPORTED_DOCUMENT
    assert "missing or invalid /Type" in result.reasons[0]
    assert not output.exists()


def test_raw_page_tree_accepts_inherited_rotation_and_preserves_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = tmp_path / "base.pdf"
    source = tmp_path / "inherited-rotation.pdf"
    output = tmp_path / "output.pdf"
    _generate_vector_pdf(base)

    def mutate(writer: PdfWriter) -> None:
        _, root = _raw_writer_pages_root(writer)
        leaf = writer.pages[0]
        leaf.pop(NameObject("/Rotate"), None)
        root[NameObject("/Rotate")] = NumberObject(90)

    _rewrite(base, source, mutate)
    _force_vector_color_diagnosis(monkeypatch)
    result = fit_color_vector_pdf(source, output, target_bytes=_fit_target(source))

    assert result.status is ColorFitStatus.FITTED
    assert int(PdfReader(str(output)).pages[0].get("/Rotate", 0)) == 90


def test_raw_page_tree_accepts_inherited_mediabox_and_preserves_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = tmp_path / "base.pdf"
    source = tmp_path / "inherited-mediabox.pdf"
    output = tmp_path / "output.pdf"
    _generate_vector_pdf(base, page_specs=((420.0, 595.0, 0),))

    def mutate(writer: PdfWriter) -> None:
        _, root = _raw_writer_pages_root(writer)
        leaf = writer.pages[0]
        mediabox = leaf.raw_get("/MediaBox")
        del leaf[NameObject("/MediaBox")]
        root[NameObject("/MediaBox")] = mediabox

    _rewrite(base, source, mutate)
    _force_vector_color_diagnosis(monkeypatch)
    result = fit_color_vector_pdf(source, output, target_bytes=_fit_target(source))

    assert result.status is ColorFitStatus.FITTED
    output_box = tuple(
        float(value) for value in PdfReader(str(output)).pages[0].mediabox
    )
    assert output_box == (0.0, 0.0, 420.0, 595.0)


@pytest.mark.parametrize(
    ("fixture_name", "mutate", "reason_fragment"),
    [
        (
            "certified.pdf",
            lambda writer: writer.root_object.__setitem__(
                NameObject("/Perms"), DictionaryObject()
            ),
            "signature field or certification",
        ),
        (
            "acroform.pdf",
            lambda writer: writer.root_object.__setitem__(
                NameObject("/AcroForm"),
                DictionaryObject(
                    {
                        NameObject("/Fields"): ArrayObject(
                            [DictionaryObject({NameObject("/FT"): NameObject("/Tx")})]
                        )
                    }
                ),
            ),
            "AcroForm fields",
        ),
        (
            "annotation.pdf",
            lambda writer: writer.pages[0].__setitem__(
                NameObject("/Annots"),
                ArrayObject(
                    [
                        DictionaryObject(
                            {
                                NameObject("/Subtype"): NameObject("/Text"),
                                NameObject("/Contents"): TextStringObject("note"),
                            }
                        )
                    ]
                ),
            ),
            "annotations",
        ),
        (
            "outline.pdf",
            lambda writer: writer.add_outline_item("Page 1", 0),
            "outlines/bookmarks",
        ),
        (
            "bad-rotation.pdf",
            lambda writer: writer.pages[0].__setitem__(
                NameObject("/Rotate"), NumberObject(45)
            ),
            "multiple of 90",
        ),
    ],
)
def test_fail_closed_safety_refusals(
    tmp_path: Path,
    fixture_name: str,
    mutate,
    reason_fragment: str,
) -> None:
    base = tmp_path / "base.pdf"
    source = tmp_path / fixture_name
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_pdf(base)
    _rewrite(base, source, mutate)

    result = fit_color_vector_pdf(source, output, target_bytes=1)

    assert result.status is ColorFitStatus.UNSUPPORTED_DOCUMENT
    assert reason_fragment in result.reasons[0]
    assert not output.exists()


@pytest.mark.parametrize(
    ("fixture_name", "mutate", "reason_fragment"),
    [
        (
            "catalog-lang.pdf",
            lambda writer: writer.root_object.__setitem__(
                NameObject("/Lang"), TextStringObject("en-US")
            ),
            "/Lang",
        ),
        (
            "catalog-metadata.pdf",
            lambda writer: writer.root_object.__setitem__(
                NameObject("/Metadata"), writer._add_object(_non_pdfa_metadata())
            ),
            "/Metadata",
        ),
        (
            "empty-acroform.pdf",
            lambda writer: writer.root_object.__setitem__(
                NameObject("/AcroForm"), DictionaryObject()
            ),
            "AcroForm structure",
        ),
        (
            "page-struct-parents.pdf",
            lambda writer: writer.pages[0].__setitem__(
                NameObject("/StructParents"), NumberObject(0)
            ),
            "/StructParents",
        ),
        (
            "page-group.pdf",
            lambda writer: writer.pages[0].__setitem__(
                NameObject("/Group"), DictionaryObject()
            ),
            "/Group",
        ),
        (
            "custom-catalog-key.pdf",
            lambda writer: writer.root_object.__setitem__(
                NameObject("/CustomCatalogSemantics"), NumberObject(1)
            ),
            "/CustomCatalogSemantics",
        ),
        (
            "custom-page-key.pdf",
            lambda writer: writer.pages[0].__setitem__(
                NameObject("/CustomPageSemantics"), NumberObject(1)
            ),
            "/CustomPageSemantics",
        ),
    ],
)
def test_fit_refuses_unreconstructed_catalog_and_page_semantics(
    tmp_path: Path,
    fixture_name: str,
    mutate,
    reason_fragment: str,
) -> None:
    base = tmp_path / "base.pdf"
    source = tmp_path / fixture_name
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_pdf(base)
    _rewrite(base, source, mutate)

    result = fit_color_vector_pdf(source, output, target_bytes=1)

    assert result.status is ColorFitStatus.UNSUPPORTED_DOCUMENT
    assert reason_fragment in result.reasons[0]
    assert not output.exists()


def test_fit_refuses_signature_field(tmp_path: Path) -> None:
    base = tmp_path / "base.pdf"
    source = tmp_path / "signature.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_pdf(base)

    def add_signature(writer: PdfWriter) -> None:
        field = DictionaryObject({NameObject("/FT"): NameObject("/Sig")})
        writer.root_object[NameObject("/AcroForm")] = DictionaryObject(
            {NameObject("/Fields"): ArrayObject([field])}
        )

    _rewrite(base, source, add_signature)
    result = fit_color_vector_pdf(source, output, target_bytes=1)

    assert result.status is ColorFitStatus.UNSUPPORTED_DOCUMENT
    assert "signature field" in result.reasons[0]
    assert not output.exists()


def test_fit_refuses_embedded_file(tmp_path: Path) -> None:
    base = tmp_path / "base.pdf"
    source = tmp_path / "attachment.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_pdf(base)
    _rewrite(base, source, lambda writer: writer.add_attachment("note.txt", b"private"))

    result = fit_color_vector_pdf(source, output, target_bytes=1)

    assert result.status is ColorFitStatus.UNSUPPORTED_DOCUMENT
    assert "embedded files" in result.reasons[0]
    assert not output.exists()


def test_fit_refuses_pdfa_identification_metadata(tmp_path: Path) -> None:
    base = tmp_path / "base.pdf"
    source = tmp_path / "pdfa.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_pdf(base)

    def add_pdfa(writer: PdfWriter) -> None:
        writer.xmp_metadata = b"""<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
<rdf:Description xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/">
<pdfaid:part>2</pdfaid:part><pdfaid:conformance>B</pdfaid:conformance>
</rdf:Description></rdf:RDF>"""

    _rewrite(base, source, add_pdfa)
    result = fit_color_vector_pdf(source, output, target_bytes=1)

    assert result.status is ColorFitStatus.UNSUPPORTED_DOCUMENT
    assert "PDF/A" in result.reasons[0]
    assert not output.exists()


def test_fit_refuses_encrypted_pdf(tmp_path: Path) -> None:
    base = tmp_path / "base.pdf"
    source = tmp_path / "encrypted.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_pdf(base)

    writer = PdfWriter(clone_from=str(base))
    writer.encrypt("secret")
    with source.open("wb") as encrypted:
        writer.write(encrypted)

    result = fit_color_vector_pdf(source, output, target_bytes=1)

    assert result.status is ColorFitStatus.UNSUPPORTED_DOCUMENT
    assert "encrypted" in result.reasons[0]
    assert not output.exists()


def test_fit_refuses_different_cropbox(tmp_path: Path) -> None:
    base = tmp_path / "base.pdf"
    source = tmp_path / "cropped.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_pdf(base)

    def crop(writer: PdfWriter) -> None:
        writer.pages[0][NameObject("/CropBox")] = RectangleObject([10, 10, 580, 820])

    _rewrite(base, source, crop)
    result = fit_color_vector_pdf(source, output, target_bytes=1)

    assert result.status is ColorFitStatus.UNSUPPORTED_DOCUMENT
    assert "CropBox" in result.reasons[0]
    assert not output.exists()


def test_result_helper_without_explicit_jpeg_quality_has_none_default():
    from pdf_size_fit.color_fit import _result, ColorFitStatus
    from pathlib import Path

    res = _result(
        ColorFitStatus.SKIP,
        Path("input.pdf"),
        input_size=10,
        target_bytes=5,
        page_count=1,
        reasons=(),
    )
    assert res.jpeg_quality is None


def test_color_emits_page_progress_for_each_page(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "output.pdf"
    _generate_vector_pdf(
        source,
        color=True,
        page_specs=((595.0, 842.0, 0), (595.0, 842.0, 0), (595.0, 842.0, 0)),
    )

    events: list[ProgressEvent] = []

    result = fit_color_vector_pdf(
        source,
        output,
        target_bytes=_fit_target(source),
        progress_callback=events.append,
    )

    assert result.status is ColorFitStatus.FITTED
    assert len(events) == 3
    assert events == [
        ProgressEvent(phase=ProgressPhase.PAGE_OPTIMIZATION, completed=1, total=3),
        ProgressEvent(phase=ProgressPhase.PAGE_OPTIMIZATION, completed=2, total=3),
        ProgressEvent(phase=ProgressPhase.PAGE_OPTIMIZATION, completed=3, total=3),
    ]


def test_color_callback_exception_does_not_affect_result(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "output.pdf"
    _generate_vector_pdf(source, color=True)

    def buggy_callback(event: ProgressEvent) -> None:
        raise RuntimeError("color callback error")

    result = fit_color_vector_pdf(
        source,
        output,
        target_bytes=_fit_target(source),
        progress_callback=buggy_callback,
    )

    assert result.status is ColorFitStatus.FITTED
    assert output.exists()
