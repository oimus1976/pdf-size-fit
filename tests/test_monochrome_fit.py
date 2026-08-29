from __future__ import annotations

import hashlib
from pathlib import Path

import pypdfium2
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

from pdf_size_fit.monochrome_fit import (
    MonochromeFitStatus,
    fit_monochrome_vector_pdf,
)


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


def _generate_gray_vector_pdf(path: Path) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    stream = DecodedStreamObject()
    stream.set_data(b"0.5 g 0 0 595 842 re f")
    page.replace_contents(stream)
    with path.open("wb") as output:
        writer.write(output)


def _rewrite(source: Path, destination: Path, mutate) -> None:
    writer = PdfWriter(clone_from=str(source))
    mutate(writer)
    with destination.open("wb") as output:
        writer.write(output)


def _fit_target(source: Path) -> int:
    return source.stat().st_size - 1


def test_successful_fixed_300_dpi_monochrome_fit_is_1bit_ccitt_g4(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "output.pdf"
    _generate_vector_pdf(source)
    before_hash = _sha256(source)

    result = fit_monochrome_vector_pdf(source, output, target_bytes=_fit_target(source))

    assert result.status is MonochromeFitStatus.FITTED
    assert result.dpi == 300
    assert result.bits_per_pixel == 1
    assert result.compression == "CCITT Group 4"
    assert result.output_size_bytes is not None
    assert result.output_size_bytes <= result.target_bytes
    assert output.exists()
    assert _sha256(source) == before_hash

    image = PdfReader(str(output)).pages[0].images[0]
    image_object = image.indirect_reference.get_object()
    filters = image_object["/Filter"]
    assert list(filters) == ["/CCITTFaxDecode"]
    assert image_object["/BitsPerComponent"] == 1
    decode_params = image_object["/DecodeParms"][0]
    assert decode_params["/K"] == -1
    assert bool(decode_params["/BlackIs1"])


def test_fit_refuses_to_overwrite_source_or_existing_output(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "existing.pdf"
    _generate_vector_pdf(source)
    output.write_bytes(b"keep me")

    with pytest.raises(ValueError, match="must differ"):
        fit_monochrome_vector_pdf(source, source, target_bytes=_fit_target(source))
    with pytest.raises(FileExistsError, match="already exists"):
        fit_monochrome_vector_pdf(source, output, target_bytes=_fit_target(source))

    assert output.read_bytes() == b"keep me"


def test_fit_skips_input_already_below_target(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_pdf(source, repeats=10)

    result = fit_monochrome_vector_pdf(
        source,
        output,
        target_bytes=source.stat().st_size,
    )

    assert result.status is MonochromeFitStatus.SKIP
    assert not output.exists()


def test_fit_requires_existing_vector_monochrome_diagnosis(tmp_path: Path) -> None:
    source = tmp_path / "color.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_pdf(source, color=True)

    result = fit_monochrome_vector_pdf(source, output, target_bytes=_fit_target(source))

    assert result.status is MonochromeFitStatus.ROUTE_MISMATCH
    assert "vector-color" in result.reasons[0]
    assert not output.exists()


def test_fit_refuses_non_whitespace_extractable_text(tmp_path: Path) -> None:
    source = tmp_path / "extractable-text.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_text_pdf(source, "searchable text")

    result = fit_monochrome_vector_pdf(source, output, target_bytes=1)

    assert result.status is MonochromeFitStatus.UNSUPPORTED_DOCUMENT
    assert "selectable/searchable text" in result.reasons[0]
    assert not output.exists()


def test_whitespace_extractable_text_does_not_by_itself_refuse(tmp_path: Path) -> None:
    source = tmp_path / "whitespace-text.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_text_pdf(source, "   ")

    result = fit_monochrome_vector_pdf(source, output, target_bytes=1)

    assert "extractable text" not in result.reasons[0]
    assert result.status is not MonochromeFitStatus.UNSUPPORTED_DOCUMENT
    assert not output.exists()


def test_fit_refuses_material_grayscale_midtone_content(tmp_path: Path) -> None:
    source = tmp_path / "gray-vector.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_gray_vector_pdf(source)

    result = fit_monochrome_vector_pdf(source, output, target_bytes=1)

    assert result.status is MonochromeFitStatus.UNSUPPORTED_DOCUMENT
    assert "material grayscale/midtone content" in result.reasons[0]
    assert not output.exists()


def test_existing_black_white_vector_fixture_remains_eligible(tmp_path: Path) -> None:
    source = tmp_path / "black-white-vector.pdf"
    output = tmp_path / "output.pdf"
    _generate_vector_pdf(source)

    result = fit_monochrome_vector_pdf(source, output, target_bytes=_fit_target(source))

    assert result.status is MonochromeFitStatus.FITTED
    assert output.exists()


def test_bilevel_render_failure_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_pdf(source)

    def fail_to_open(_path: str):
        raise RuntimeError("synthetic PDFium failure")

    monkeypatch.setattr(pypdfium2, "PdfDocument", fail_to_open)
    result = fit_monochrome_vector_pdf(source, output, target_bytes=1)

    assert result.status is MonochromeFitStatus.UNSUPPORTED_DOCUMENT
    assert "bilevel-suitability" in result.reasons[0]
    assert not output.exists()


def test_target_not_met_does_not_search_dpi_or_write_output(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_pdf(source)

    result = fit_monochrome_vector_pdf(source, output, target_bytes=1)

    assert result.status is MonochromeFitStatus.TARGET_NOT_MET
    assert result.dpi == 300
    assert "DPI was not reduced or searched" in result.reasons[1]
    assert not output.exists()


def test_non_300_dpi_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "output.pdf"
    _generate_vector_pdf(source)

    with pytest.raises(ValueError, match="exactly 300"):
        fit_monochrome_vector_pdf(source, output, dpi=299)


def test_page_count_size_and_rotation_are_preserved(tmp_path: Path) -> None:
    source = tmp_path / "mixed-pages.pdf"
    output = tmp_path / "output.pdf"
    _generate_vector_pdf(
        source,
        page_specs=((595.0, 842.0, 0), (420.0, 595.0, 90)),
    )
    source_reader = PdfReader(str(source))

    result = fit_monochrome_vector_pdf(source, output, target_bytes=_fit_target(source))

    assert result.status is MonochromeFitStatus.FITTED
    output_reader = PdfReader(str(output))
    assert len(output_reader.pages) == len(source_reader.pages) == 2
    assert [tuple(float(v) for v in p.mediabox) for p in output_reader.pages] == [
        tuple(float(v) for v in p.mediabox) for p in source_reader.pages
    ]
    assert [int(p.get("/Rotate", 0)) for p in output_reader.pages] == [0, 90]


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

    result = fit_monochrome_vector_pdf(source, output, target_bytes=1)

    assert result.status is MonochromeFitStatus.UNSUPPORTED_DOCUMENT
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
    result = fit_monochrome_vector_pdf(source, output, target_bytes=1)

    assert result.status is MonochromeFitStatus.UNSUPPORTED_DOCUMENT
    assert "signature field" in result.reasons[0]
    assert not output.exists()


def test_fit_refuses_embedded_file(tmp_path: Path) -> None:
    base = tmp_path / "base.pdf"
    source = tmp_path / "attachment.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_pdf(base)
    _rewrite(base, source, lambda writer: writer.add_attachment("note.txt", b"private"))

    result = fit_monochrome_vector_pdf(source, output, target_bytes=1)

    assert result.status is MonochromeFitStatus.UNSUPPORTED_DOCUMENT
    assert "embedded files" in result.reasons[0]
    assert not output.exists()


def test_fit_refuses_pdfa_identification_metadata(tmp_path: Path) -> None:
    base = tmp_path / "base.pdf"
    source = tmp_path / "pdfa.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_pdf(base)

    def add_pdfa(writer: PdfWriter) -> None:
        writer.xmp_metadata = b'''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
<rdf:Description xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/">
<pdfaid:part>2</pdfaid:part><pdfaid:conformance>B</pdfaid:conformance>
</rdf:Description></rdf:RDF>'''

    _rewrite(base, source, add_pdfa)
    result = fit_monochrome_vector_pdf(source, output, target_bytes=1)

    assert result.status is MonochromeFitStatus.UNSUPPORTED_DOCUMENT
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

    result = fit_monochrome_vector_pdf(source, output, target_bytes=1)

    assert result.status is MonochromeFitStatus.UNSUPPORTED_DOCUMENT
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
    result = fit_monochrome_vector_pdf(source, output, target_bytes=1)

    assert result.status is MonochromeFitStatus.UNSUPPORTED_DOCUMENT
    assert "CropBox" in result.reasons[0]
    assert not output.exists()
