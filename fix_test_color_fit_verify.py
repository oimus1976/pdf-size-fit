with open('tests/test_color_fit.py', 'r') as f:
    lines = f.readlines()

start = -1
for i, line in enumerate(lines):
    if line.startswith('def test_output_render_failure_fails_closed_and_leaves_no_output('):
        if start == -1:
            start = i
        else:
            # We found the second duplicate.
            # remove it.
            del lines[start:]
            break

with open('tests/test_color_fit.py', 'w') as f:
    f.writelines(lines)
