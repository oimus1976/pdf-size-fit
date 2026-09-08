with open('src/pdf_size_fit/color_fit.py', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if line.strip() == 'searchable_text_semantics_lost: bool | None = None,':
        del lines[i]
        break

with open('src/pdf_size_fit/color_fit.py', 'w') as f:
    f.writelines(lines)
