with open('tests/test_color_fit.py', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if line.strip() == 'monkeypatch.setattr(' and lines[i-1] == '            lambda *_args: (((2, 2),), None),\n':
        lines[i-1] = '            lambda *_args: (((2, 2),), None),\n        )\n'
        break

with open('tests/test_color_fit.py', 'w') as f:
    f.writelines(lines)
