with open('tests/test_color_fit.py', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if line.startswith('def _generate_vector_text_pdf('):
        end_idx = i
        while not lines[end_idx].strip() == 'writer.write(output)':
            end_idx += 1
        lines[i:end_idx+1] = [
            'def _generate_vector_text_pdf(\n',
            '    path: Path,\n',
            '    pages: tuple[tuple[str, ...], ...],\n',
            '    color: bool = True,\n',
            '    repeats: int = 1,\n',
            ') -> None:\n',
            '    writer = PdfWriter()\n',
            '    stroke = b"0.8 0.1 0.1 RG\\n" if color else b"0 G\\n"\n',
            '    for text_lines in pages:\n',
            '        page = writer.add_blank_page(width=595.0, height=842.0)\n',
            '        drawing = []\n',
            '        for line in text_lines:\n',
            '            drawing.append(b"40 40 m 540 790 l S\\n" * repeats)\n',
            '            drawing.append(b"BT /F1 12 Tf 100 100 Td (" + line.encode("latin-1") + b") Tj ET\\n")\n',
            '        stream = DecodedStreamObject()\n',
            '        stream.set_data(stroke + b"0.5 w\\n" + b"".join(drawing))\n',
            '        page.replace_contents(stream)\n',
            '    with path.open("wb") as output:\n',
            '        writer.write(output)\n'
        ]
        break

with open('tests/test_color_fit.py', 'w') as f:
    f.writelines(lines)
