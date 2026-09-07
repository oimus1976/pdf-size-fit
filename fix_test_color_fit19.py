with open('tests/test_color_fit.py', 'r') as f:
    content = f.read()

content = content.replace(
    '        monkeypatch.setattr(\n            color_fit,\n            "_pdfium_text_metrics",\n            lambda *_args: (((0, 0),), None),\n        )',
    '        monkeypatch.setattr(\n            color_fit,\n            "_pdfium_text_metrics",\n            lambda *_args: (((2, 2),), None),\n        )\n        monkeypatch.setattr(\n            color_fit,\n            "_pypdf_text_metrics",\n            lambda *_args: (((2, 2),), None),\n        )'
)

with open('tests/test_color_fit.py', 'w') as f:
    f.write(content)
