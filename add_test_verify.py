with open('tests/test_color_fit.py', 'r') as f:
    content = f.read()

# Add test for verify_candidate pdfium rendering
new_test = '''def test_output_render_failure_fails_closed_and_leaves_no_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "output.pdf"
    _generate_vector_pdf(source, color=True)

    import pypdfium2 as pdfium

    original_render = pdfium.PdfPage.render
    def failing_render(self, *args, **kwargs):
        failing_render.calls += 1
        if failing_render.calls > 1:
            raise RuntimeError("synthetic render failure")
        return original_render(self, *args, **kwargs)

    failing_render.calls = 0

    monkeypatch.setattr("pypdfium2.PdfPage.render", failing_render)

    with pytest.raises(RuntimeError, match="synthetic render failure"):
        fit_color_vector_pdf(source, output, target_bytes=10_000_000)

    assert not output.exists()
'''

content += "\n" + new_test

# test searchable semantics result tracking
content = content.replace(
    '        assert result.output_size_bytes is not None\n        assert result.output_size_bytes <= result.target_bytes',
    '        assert result.output_size_bytes is not None\n        assert result.output_size_bytes <= result.target_bytes\n        assert result.searchable_text_semantics_lost is False'
)

# in test_text_opt_in_fits_small_repeated_searchable_layer
content = content.replace(
    '        assert result.status is ColorFitStatus.FITTED\n    ',
    '        assert result.status is ColorFitStatus.FITTED\n        assert result.searchable_text_semantics_lost is True\n    '
)

with open('tests/test_color_fit.py', 'w') as f:
    f.write(content)
