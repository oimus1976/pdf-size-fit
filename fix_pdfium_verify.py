with open('src/pdf_size_fit/color_fit.py', 'r') as f:
    lines = f.readlines()

new_lines = []
skip = False
for line in lines:
    if line.startswith('    pdf = pdfium.PdfDocument(str(candidate_path))'):
        skip = True
        continue

    if skip and line.strip() == 'pdf.close()':
        skip = False
        continue

    if not skip:
        new_lines.append(line)

new_func = '''    pdf = pdfium.PdfDocument(str(candidate_path))
    try:
        if len(pdf) != len(source.pages):
            raise RuntimeError("candidate page count disagrees with pypdf source")
        for i in range(len(pdf)):
            page = pdf[i]
            bitmap = None
            try:
                bitmap = page.render(scale=1.0)
            except Exception as e:
                raise RuntimeError(f"candidate page {i + 1} failed PDFium rendering: {e}")
            finally:
                if bitmap is not None:
                    bitmap.close()
                page.close()
    finally:
        pdf.close()
'''

for i, line in enumerate(new_lines):
    if 'raise RuntimeError(f"candidate page {index} is not RGB JPEG")' in line:
        new_lines.insert(i + 1, '\n' + new_func)
        break

with open('src/pdf_size_fit/color_fit.py', 'w') as f:
    f.writelines(new_lines)
