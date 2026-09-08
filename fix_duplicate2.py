with open('src/pdf_size_fit/color_fit.py', 'r') as f:
    lines = f.readlines()

to_remove = []
count = 0
for i, line in enumerate(lines):
    if line.strip() == 'searchable_text_semantics_lost: bool | None = None,':
        count += 1
        if count > 1:
            to_remove.append(i)

for i in reversed(to_remove):
    del lines[i]

with open('src/pdf_size_fit/color_fit.py', 'w') as f:
    f.writelines(lines)
