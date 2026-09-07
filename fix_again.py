import re

with open('tests/test_color_fit.py', 'r') as f:
    content = f.read()
content = content.replace('    assert result.bits_per_pixel == 1\n    assert result.compression == "CCITT Group 4"', '    assert result.jpeg_quality == 90')
with open('tests/test_color_fit.py', 'w') as f:
    f.write(content)
