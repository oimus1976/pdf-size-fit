import re

with open('src/pdf_size_fit/color_fit.py', 'r') as f:
    content = f.read()

content = content.replace(
    '    route: str\n    dpi: int | None = None\n    jpeg_quality: int | None = None\n    page_count: int\n    reasons: tuple[str, ...]',
    '    route: str\n    page_count: int\n    reasons: tuple[str, ...]\n    dpi: int | None = None\n    jpeg_quality: int | None = None'
)

with open('src/pdf_size_fit/color_fit.py', 'w') as f:
    f.write(content)
