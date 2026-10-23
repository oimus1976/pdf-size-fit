"""Synthetic regressions converted from the independent L2's two reproductions."""
from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path
import tempfile

import pytest
import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject, DecodedStreamObject, DictionaryObject as D, NameObject as N, NumberObject,
)

import pdf_size_fit.fit as integrated
import pdf_size_fit.monochrome_fit as mono
from pdf_size_fit.fit import FitStatus, fit_pdf
from pdf_size_fit.monochrome_fit import fit_monochrome_vector_pdf
from pdf_size_fit.source_version import SourceChangedError


def synthetic(labels, *, annotation=False, size=500000):
    writer = PdfWriter()
    font = writer._add_object(D({N('/Type'): N('/Font'), N('/Subtype'): N('/Type1'), N('/BaseFont'): N('/Helvetica')}))
    for label in labels:
        page = writer.add_blank_page(200, 200)
        page[N('/Resources')] = D({N('/Font'): D({N('/F1'): font})})
        stream = DecodedStreamObject()
        stream.set_data(b'0 G 10 10 m 190 190 l S\n%' + b'X' * (300000 // len(labels))
                        + b'\nBT /F1 12 Tf 20 150 Td (' + label + b') Tj ET')
        page.replace_contents(stream)
        if annotation:
            page[N('/Annots')] = ArrayObject([writer._add_object(D({
                N('/Type'): N('/Annot'), N('/Subtype'): N('/Text'),
                N('/Rect'): ArrayObject([NumberObject(x) for x in (20, 20, 40, 40)]),
            }))])
    buffer = BytesIO()
    writer.write(buffer)
    raw = buffer.getvalue()
    assert len(raw) + 2 <= size
    return raw + b'\n%' + b'P' * (size - len(raw) - 2)


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    directory = tmp_path / 'private-temp'
    directory.mkdir()
    monkeypatch.setattr(tempfile, 'tempdir', str(directory))
    return directory


def fit(source, output, direct=False, **kwargs):
    function = fit_monochrome_vector_pdf if direct else fit_pdf
    return function(source, output, target_bytes=499999,
                    allow_small_searchable_text_rasterization=True,
                    **({} if direct else {'decision_viewing': True}), **kwargs)


@pytest.mark.parametrize('direct', [False, True])
def test_l2_mixed_version_repro_now_refuses_publication(tmp_path, scratch, direct):
    source, output = tmp_path / 'source.pdf', tmp_path / 'out.pdf'
    source.write_bytes(synthetic([b'OLD1', b'OLD2']))
    new = synthetic([b'NEW1', b'NEW2'])
    old_stat = source.stat()
    events = []
    def change_after_first_page(event):
        events.append(event)
        if len(events) == 1:
            source.write_bytes(new)
            os.utime(source, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
    with pytest.raises(SourceChangedError, match='もう一度'):
        fit(source, output, direct, progress_callback=change_after_first_page)
    assert len(events) == 2 and source.read_bytes() == new
    assert not output.exists() and not list(scratch.iterdir())


@pytest.mark.parametrize('direct', [False, True])
@pytest.mark.parametrize('annotation', [False, True])
def test_l2_unsafe_replacement_after_real_gate_is_not_rendered_or_published(
    tmp_path, scratch, monkeypatch, direct, annotation,
):
    source, replacement = tmp_path / 'source.pdf', tmp_path / 'unsafe.pdf'
    output = tmp_path / 'out.pdf'
    old = synthetic([b''])
    new = synthetic([b'ABCDEFGHIJKL'], annotation=annotation)
    source.write_bytes(old)
    replacement.write_bytes(new)
    refused = fit(replacement, tmp_path / 'refused.pdf', direct)
    assert refused.status.value != 'fitted' and not (tmp_path / 'refused.pdf').exists()
    genuine_gate = mono._bilevel_suitability_refusal
    gate_paths, render_paths = [], []
    genuine_build = mono._build_candidate
    def change_after_gate(path, specs):
        assert path != source and path.read_bytes() == old
        gate_paths.append(path)
        refusal = genuine_gate(path, specs)
        assert refusal is None
        source.write_bytes(new)  # Outside writer updates only the live original.
        return refusal
    def record_build(path, *args, **kwargs):
        render_paths.append(path)
        assert path == gate_paths[0] and path.read_bytes() == old
        return genuine_build(path, *args, **kwargs)
    monkeypatch.setattr(mono, '_bilevel_suitability_refusal', change_after_gate)
    monkeypatch.setattr(mono, '_build_candidate', record_build)
    with pytest.raises(SourceChangedError):
        fit(source, output, direct)
    assert gate_paths and render_paths and source.read_bytes() == new
    assert not output.exists() and not list(scratch.iterdir())


@pytest.mark.parametrize('stage', ['diagnosis', 'before-publish', 'during-publish', 'missing', 'permission'])
def test_change_boundaries_fail_closed_without_output(tmp_path, scratch, monkeypatch, stage):
    source, output = tmp_path / 'source.pdf', tmp_path / 'out.pdf'
    old, new = synthetic([b'OLD1']), synthetic([b'NEW1'])
    source.write_bytes(old)
    existing = tmp_path / 'existing.pdf'
    existing.write_bytes(b'existing synthetic destination')
    if stage == 'diagnosis':
        original = integrated.diagnose_pdf
        def diagnose(path, **kwargs):
            assert path != source and path.read_bytes() == old
            source.write_bytes(new)
            return original(path, **kwargs)
        monkeypatch.setattr(integrated, 'diagnose_pdf', diagnose)
    elif stage == 'during-publish':
        original = mono._copy_exclusive
        def publish(candidate, dest):
            source.write_bytes(new)
            original(candidate, dest)
        monkeypatch.setattr(mono, '_copy_exclusive', publish)
    else:
        original = mono._verify_candidate
        def verify(path, candidate):
            original(path, candidate)
            if stage == 'before-publish':
                source.write_bytes(new)
            elif stage == 'missing':
                source.unlink()
            else:
                real_open = Path.open
                def deny(p, *args, **kwargs):
                    if p == source:
                        raise PermissionError('synthetic source permission denied')
                    return real_open(p, *args, **kwargs)
                monkeypatch.setattr(Path, 'open', deny)
        monkeypatch.setattr(mono, '_verify_candidate', verify)
    with pytest.raises(SourceChangedError):
        fit(source, output)
    assert not output.exists() and not list(scratch.iterdir())
    assert existing.read_bytes() == b'existing synthetic destination'
    if stage not in ('missing', 'permission'):
        assert source.read_bytes() == new


def test_all_pdf_consumers_use_the_same_snapshot_and_results_keep_original(tmp_path, scratch, monkeypatch):
    source, output = tmp_path / 'source.pdf', tmp_path / 'out.pdf'
    raw = synthetic([b'ABCD', b'EFGH'])
    source.write_bytes(raw)
    seen = []
    for module, name in ((integrated, 'diagnose_pdf'), (mono, 'diagnose_pdf'),
                         (mono, 'PdfReader'), (pdfium, 'PdfDocument')):
        original = getattr(module, name)
        def record(path, *args, _original=original, **kwargs):
            if isinstance(path, (str, Path)):
                seen.append(Path(path))
            return _original(path, *args, **kwargs)
        monkeypatch.setattr(module, name, record)
    result = fit(source, output)
    assert result.status is FitStatus.FITTED
    inputs = [path for path in seen if path != output and path.name != 'candidate-300dpi-g4.pdf']
    assert len(inputs) >= 6 and len(set(inputs)) == 1 and source not in seen
    assert result.input_path == str(source) and result.route_result.input_path == str(source)
    assert str(scratch) not in str(result.to_dict())
    assert source.read_bytes() == raw and not list(scratch.iterdir())
    assert len(PdfReader(output).pages) == 2


def test_stable_47_page_viewing_source_remains_supported(tmp_path, scratch):
    source, output = tmp_path / 'source.pdf', tmp_path / 'out.pdf'
    raw = synthetic([b'%04d' % i for i in range(47)])
    source.write_bytes(raw)
    result = fit(source, output)
    assert result.status is FitStatus.FITTED and result.route_result.page_count == 47
    assert result.route_result.dpi == 300 and result.route_result.bits_per_pixel == 1
    assert len(PdfReader(output).pages) == 47 and output.stat().st_size <= 499999
    assert source.read_bytes() == raw and not list(scratch.iterdir())


def test_publication_collision_keeps_competing_file_and_cleans_snapshot(tmp_path, scratch, monkeypatch):
    source, output = tmp_path / 'source.pdf', tmp_path / 'out.pdf'
    raw = synthetic([b'ABCD'])
    source.write_bytes(raw)
    original = mono._copy_exclusive
    def competing_writer(candidate, destination):
        destination.write_bytes(b'competing writer')
        original(candidate, destination)
    monkeypatch.setattr(mono, '_copy_exclusive', competing_writer)
    with pytest.raises(FileExistsError):
        fit(source, output)
    assert output.read_bytes() == b'competing writer' and source.read_bytes() == raw
    assert not list(scratch.iterdir())
