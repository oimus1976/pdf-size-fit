from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    DictionaryObject,
    NameObject,
    NumberObject,
)
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from pdf_size_fit.image_fit import ImageFitStatus, fit_image_heavy_pdf
from tools.generate_fixtures import generate_image_heavy, generate_vector


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _generate_transparent_image_pdf(path: Path, size: int = 200) -> None:
    image = Image.new("RGBA", (size, size))
    pixels = image.load()
    for y in range(size):
        for x in range(size):
            z = (x * 2654435761 + y * 2246822519) & 0xFFFFFFFF
            pixels[x, y] = (
                (z >> 16) & 255,
                (z >> 8) & 255,
                z & 255,
                80 + ((x + y) % 176),
            )

    c = canvas.Canvas(str(path), pagesize=A4, pageCompression=1)
    c.setTitle("image-fit-structure-test")
    c.drawImage(ImageReader(image), 0, 0, width=A4[0], height=A4[1], mask="auto")
    c.linkURL("https://example.invalid/", (20, 20, 100, 40), relative=0)
    c.save()


def test_fit_image_heavy_pdf_finds_highest_quality_in_refinement(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "output.pdf"
    generate_image_heavy(source, pages=1, image_size=200)
    before_hash = _sha256(source)

    result = fit_image_heavy_pdf(source, output, target_bytes=140_000, min_quality=70)

    assert result.status is ImageFitStatus.FITTED
    assert result.selected_quality == 98
    assert result.output_size_bytes is not None and result.output_size_bytes <= 140_000
    assert [attempt.quality for attempt in result.attempts] == [100, 95, 99, 98]
    assert result.images_replaced == 1
    assert output.exists()
    assert _sha256(source) == before_hash


def test_fit_preserves_soft_mask_and_non_image_structure(tmp_path: Path) -> None:
    source = tmp_path / "transparent.pdf"
    output = tmp_path / "transparent-fit.pdf"
    _generate_transparent_image_pdf(source)

    source_reader = PdfReader(str(source))
    source_image = source_reader.pages[0].images[0]
    source_obj = source_image.indirect_reference.get_object()
    source_mask_data = source_obj["/SMask"].get_object().get_data()
    source_annotations = len(source_reader.pages[0].get("/Annots", []))
    source_title = source_reader.metadata.title

    result = fit_image_heavy_pdf(source, output, target_bytes=140_000, min_quality=70)
    assert result.status is ImageFitStatus.FITTED

    output_reader = PdfReader(str(output))
    output_image = output_reader.pages[0].images[0]
    output_obj = output_image.indirect_reference.get_object()
    assert "/SMask" in output_obj
    assert output_obj["/SMask"].get_object().get_data() == source_mask_data
    assert len(output_reader.pages[0].get("/Annots", [])) == source_annotations
    assert output_reader.metadata.title == source_title
    assert tuple(float(x) for x in output_reader.pages[0].mediabox) == tuple(
        float(x) for x in source_reader.pages[0].mediabox
    )


def test_fit_does_not_write_when_already_below_target(tmp_path: Path) -> None:
    source = tmp_path / "small.pdf"
    output = tmp_path / "should-not-exist.pdf"
    generate_image_heavy(source, pages=1, image_size=100)

    result = fit_image_heavy_pdf(source, output, target_bytes=source.stat().st_size + 1)

    assert result.status is ImageFitStatus.ALREADY_BELOW_TARGET
    assert not output.exists()


def test_fit_fails_closed_on_route_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "vector.pdf"
    output = tmp_path / "should-not-exist.pdf"
    generate_vector(source, color=True, pages=1, repeats=3000)

    result = fit_image_heavy_pdf(source, output, target_bytes=20_000)

    assert result.status is ImageFitStatus.ROUTE_MISMATCH
    assert not output.exists()


def test_fit_refuses_signature_field_pdf(tmp_path: Path) -> None:
    base = tmp_path / "base.pdf"
    source = tmp_path / "signed-structure.pdf"
    output = tmp_path / "should-not-exist.pdf"
    generate_image_heavy(base, pages=1, image_size=300)

    writer = PdfWriter(clone_from=str(base))
    signature_field = DictionaryObject({NameObject("/FT"): NameObject("/Sig")})
    writer.root_object[NameObject("/AcroForm")] = DictionaryObject(
        {NameObject("/Fields"): ArrayObject([signature_field])}
    )
    with source.open("wb") as f:
        writer.write(f)

    result = fit_image_heavy_pdf(source, output, target_bytes=100_000, min_quality=70)

    assert result.status is ImageFitStatus.SIGNED_PDF_UNSUPPORTED
    assert not output.exists()


def test_fit_preserves_supported_image_dictionary_semantics(tmp_path: Path) -> None:
    base = tmp_path / "base.pdf"
    source = tmp_path / "source.pdf"
    output = tmp_path / "output.pdf"
    generate_image_heavy(base, pages=1, image_size=300)

    writer = PdfWriter(clone_from=str(base))
    image = writer.pages[0].images[0]
    obj = image.indirect_reference.get_object()
    obj[NameObject("/Interpolate")] = BooleanObject(True)
    obj[NameObject("/StructParent")] = NumberObject(7)
    with source.open("wb") as f:
        writer.write(f)

    result = fit_image_heavy_pdf(source, output, target_bytes=170_000, min_quality=70)

    assert result.status is ImageFitStatus.FITTED
    out_obj = PdfReader(str(output)).pages[0].images[0].indirect_reference.get_object()
    assert out_obj["/Interpolate"] == BooleanObject(True)
    assert int(out_obj["/StructParent"]) == 7


def _noise_image(size: int) -> Image.Image:
    image = Image.new("RGB", (size, size))
    pixels = image.load()
    for y in range(size):
        for x in range(size):
            z = (x * 2654435761 + y * 2246822519) & 0xFFFFFFFF
            pixels[x, y] = ((z >> 16) & 255, (z >> 8) & 255, z & 255)
    return image


def test_fit_preserves_shared_form_image_reference(tmp_path: Path) -> None:
    source = tmp_path / "shared-form.pdf"
    output = tmp_path / "shared-form-fit.pdf"
    image = _noise_image(250)

    c = canvas.Canvas(str(source), pagesize=A4, pageCompression=1)
    c.beginForm("SharedForm", 0, 0, A4[0], A4[1])
    c.drawImage(ImageReader(image), 0, 0, width=A4[0], height=A4[1])
    c.endForm()
    for _ in range(2):
        c.doForm("SharedForm")
        c.showPage()
    c.save()

    source_reader = PdfReader(str(source))
    source_refs = [
        page.images[0].indirect_reference.idnum for page in source_reader.pages
    ]
    assert source_refs[0] == source_refs[1]

    result = fit_image_heavy_pdf(source, output, target_bytes=140_000, min_quality=70)

    assert result.status is ImageFitStatus.FITTED
    assert result.images_replaced == 1
    output_reader = PdfReader(str(output))
    output_refs = [
        page.images[0].indirect_reference.idnum for page in output_reader.pages
    ]
    assert output_refs[0] == output_refs[1]
    assert all(len(page.images.keys()[0]) == 2 for page in output_reader.pages)


def test_fit_preserves_bookmark_form_and_attachment(tmp_path: Path) -> None:
    base = tmp_path / "base-structure.pdf"
    source = tmp_path / "structure.pdf"
    output = tmp_path / "structure-fit.pdf"
    image = _noise_image(250)

    c = canvas.Canvas(str(base), pagesize=A4, pageCompression=1)
    c.bookmarkPage("page-1")
    c.addOutlineEntry("Page 1", "page-1", level=0)
    c.drawImage(ImageReader(image), 0, 0, width=A4[0], height=A4[1])
    c.acroForm.textfield(name="case_id", x=50, y=50, width=120, height=20, value="ABC")
    c.save()

    writer = PdfWriter(clone_from=str(base))
    writer.add_attachment("note.txt", b"hello attachment")
    with source.open("wb") as f:
        writer.write(f)

    result = fit_image_heavy_pdf(source, output, target_bytes=140_000, min_quality=70)

    assert result.status is ImageFitStatus.FITTED
    out_reader = PdfReader(str(output))
    assert out_reader.outline[0]["/Title"] == "Page 1"
    assert out_reader.get_fields()["case_id"]["/V"] == "ABC"
    assert out_reader.attachments["note.txt"] == [b"hello attachment"]


def test_fit_refuses_pdfa_identification_metadata(tmp_path: Path) -> None:
    base = tmp_path / "base.pdf"
    source = tmp_path / "pdfa-marked.pdf"
    output = tmp_path / "should-not-exist.pdf"
    generate_image_heavy(base, pages=1, image_size=250)

    writer = PdfWriter(clone_from=str(base))
    writer.xmp_metadata = b"""<?xpacket begin=""?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/">
      <pdfaid:part>2</pdfaid:part>
      <pdfaid:conformance>B</pdfaid:conformance>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""
    with source.open("wb") as f:
        writer.write(f)

    result = fit_image_heavy_pdf(source, output, target_bytes=140_000, min_quality=70)

    assert result.status is ImageFitStatus.PDF_A_UNSUPPORTED
    assert not output.exists()
