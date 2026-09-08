with open('src/pdf_size_fit/color_fit.py', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if line.strip() == 'jpeg_quality: int | None = None':
        lines[i] = '    jpeg_quality: int | None = None,\n'

with open('src/pdf_size_fit/color_fit.py', 'w') as f:
    f.writelines(lines)
