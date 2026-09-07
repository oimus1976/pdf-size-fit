with open('tests/test_color_fit.py', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if line.strip() == 'assert result.output_size_bytes is not None':
        lines[i] = '    assert result.output_size_bytes is not None\n'

with open('tests/test_color_fit.py', 'w') as f:
    f.writelines(lines)
