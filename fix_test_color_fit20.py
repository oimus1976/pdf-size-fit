with open('tests/test_color_fit.py', 'r') as f:
    lines = f.readlines()

# This is getting ridiculous. I will find the exact lines and change them manually by reading the file
found = False
for i, line in enumerate(lines):
    if 'def test_text_opt_in_refuses_more_than_one_non_empty_line' in line:
        found = True

    if found and 'lambda *_args: (((0, 0),), None),' in line:
        lines[i] = '            lambda *_args: (((2, 2),), None),\n        )\n        monkeypatch.setattr(\n            color_fit,\n            "_pypdf_text_metrics",\n            lambda *_args: (((2, 2),), None),\n'
        break

with open('tests/test_color_fit.py', 'w') as f:
    f.writelines(lines)
