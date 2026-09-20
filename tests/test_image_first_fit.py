from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject

from pdf_size_fit.diagnose import Route
from pdf_size_fit.image_first_fit import (
    _quality_probes,
    _scale_probes,
    fit_image_heavy_pdf_first_fit,
)
from pdf_size_fit.image_fit import ImageFitStatus, _build_candidate
from tools.generate_fixtures import generate_image_heavy


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_standard_probe_sets_are_small_ordered_and_floor_aware() -> None:
    assert _quality_probes(70) == (100, 90, 75, 70)
    assert _quality_probes(80) == (100, 90, 80)
    assert _quality_probes(95) == (100, 95)

    assert _scale_probes(1.0) == ()
    assert _scale_probes(0.83) == (90, 83)
    assert _scale_probes(0.50) == (90, 80, 70, 60, 50)


def test_first_fit_stops_at_quality_100_when_first_candidate_fits(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source.pdf"
    probe = tmp_path / "probe-q100.pdf"
    output = tmp_path / "output.pdf"
    generate_image_heavy(source, pages=1, image_size=300)
    before_hash = _sha256(source)

    _build_candidate(source, probe, quality=100, scale=1.0)

    # Candidate byte size varies with the PDF/image stack. This unit test is
    # specifically about first-fit ordering and stopping, not route diagnosis.
    target = probe.stat().st_size + 1024
    monkeypatch.setattr(
        "pdf_size_fit.image_first_fit.diagnose_pdf",
        lambda *_args, **_kwargs: SimpleNamespace(route=Route.IMAGE_HEAVY),
    )

    result = fit_image_heavy_pdf_first_fit(
        source,
        output,
        target_bytes=target,
        min_quality=70,
        min_scale=1.0,
    )

    assert result.status is ImageFitStatus.FITTED
    assert result.selected_quality == 100
    assert result.selected_scale == 1.0
    assert [(attempt.scale, attempt.quality) for attempt in result.attempts] == [
        (1.0, 100)
    ]
    assert result.output_size_bytes is not None and result.output_size_bytes <= target
    assert output.exists()
    assert _sha256(source) == before_hash


def test_first_fit_uses_bounded_scale_probes_after_quality_exhaustion(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "output.pdf"
    generate_image_heavy(source, pages=1, image_size=300)
    before_hash = _sha256(source)

    full_sizes: list[int] = []
    for quality in (100, 90, 75, 70):
        candidate = tmp_path / f"full-q{quality}.pdf"
        _build_candidate(source, candidate, quality=quality, scale=1.0)
        full_sizes.append(candidate.stat().st_size)

    scale90_q70 = tmp_path / "scale90-q70.pdf"
    _build_candidate(source, scale90_q70, quality=70, scale=0.90)
    scale90_size = scale90_q70.stat().st_size
    smallest_full_size = min(full_sizes)
    assert scale90_size < smallest_full_size
    target = (smallest_full_size + scale90_size) // 2

    result = fit_image_heavy_pdf_first_fit(
        source,
        output,
        target_bytes=target,
        min_quality=70,
        min_scale=0.50,
    )

    assert result.status is ImageFitStatus.FITTED
    assert result.selected_quality == 70
    assert result.selected_scale == 0.90
    assert [(attempt.scale, attempt.quality) for attempt in result.attempts] == [
        (1.0, 100),
        (1.0, 90),
        (1.0, 75),
        (1.0, 70),
        (0.90, 70),
    ]
    assert result.output_size_bytes is not None and result.output_size_bytes <= target
    assert output.exists()
    assert _sha256(source) == before_hash


def test_first_fit_retains_signature_fail_closed_gate(tmp_path: Path) -> None:
    base = tmp_path / "base.pdf"
    source = tmp_path / "signed-structure.pdf"
    output = tmp_path / "should-not-exist.pdf"
    generate_image_heavy(base, pages=1, image_size=300)

    writer = PdfWriter(clone_from=str(base))
    signature_field = DictionaryObject({NameObject("/FT"): NameObject("/Sig")})
    writer.root_object[NameObject("/AcroForm")] = DictionaryObject(
        {NameObject("/Fields"): ArrayObject([signature_field])}
    )
    with source.open("wb") as stream:
        writer.write(stream)

    result = fit_image_heavy_pdf_first_fit(
        source,
        output,
        target_bytes=max(1, source.stat().st_size // 2),
        min_quality=70,
        min_scale=0.50,
    )

    assert result.status is ImageFitStatus.SIGNED_PDF_UNSUPPORTED
    assert result.attempts == ()
    assert not output.exists()


def test_first_fit_retains_pdfa_fail_closed_gate(tmp_path: Path) -> None:
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
    with source.open("wb") as stream:
        writer.write(stream)

    result = fit_image_heavy_pdf_first_fit(
        source,
        output,
        target_bytes=max(1, source.stat().st_size // 2),
        min_quality=70,
        min_scale=0.50,
    )

    assert result.status is ImageFitStatus.PDF_A_UNSUPPORTED
    assert result.attempts == ()
    assert not output.exists()
