import re

with open('src/pdf_size_fit/color_fit.py', 'r') as f:
    content = f.read()

content = content.replace(
    'dpi=FIXED_COLOR_DPI if status is ColorFitStatus.FITTED else None',
    'dpi=FIXED_COLOR_DPI'
)
content = content.replace(
    'jpeg_quality=jpeg_quality if status is ColorFitStatus.FITTED else None',
    'jpeg_quality=jpeg_quality'
)

with open('src/pdf_size_fit/color_fit.py', 'w') as f:
    f.write(content)

with open('tests/test_color_fit.py', 'r') as f:
    content = f.read()

# I forgot to replace `def _generate_vector_text_pdf(` again because it was replaced incorrectly.
# Let's just blindly force it again.
content = re.sub(
    r'def _generate_vector_text_pdf\(\n    path: Path,\n    pages: tuple\[tuple\[str, \.\.\.\], \.\.\.\],\n\) -> None:\n    writer = PdfWriter\(\)\n    for text_lines in pages:\n        page = writer\.add_blank_page\(width=595\.0, height=842\.0\)\n        drawing = \[\]\n        for line in text_lines:\n            drawing\.append\(b"40 40 m 540 790 l S\\n"\)\n            drawing\.append\(b"BT /F1 12 Tf 100 100 Td \(" \+ line\.encode\("latin-1"\) \+ b"\) Tj ET\\n"\)\n        stream = DecodedStreamObject\(\)\n        stream\.set_data\(b"0 G 0\.5 w\\n" \+ b""\.join\(drawing\)\)\n        page\.replace_contents\(stream\)\n    with path\.open\("wb"\) as output:\n        writer\.write\(output\)',
    r'''def _generate_vector_text_pdf(
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
            drawing.append(b"BT /F1 12 Tf 100 100 Td (" + line.encode("latin-1") + b") Tj ET\n")
        stream = DecodedStreamObject()
        stream.set_data(stroke + b"0.5 w\n" + b"".join(drawing))
        page.replace_contents(stream)
    with path.open("wb") as output:
        writer.write(output)''',
    content,
    flags=re.DOTALL
)

with open('tests/test_color_fit.py', 'w') as f:
    f.write(content)
