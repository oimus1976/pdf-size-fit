import re

with open('src/pdf_size_fit/color_fit.py', 'r') as f:
    content = f.read()

# Fix the syntax error in `b"q\n"` replacement earlier.
# The problem is that when I did my redo script, I used `b"q\n"` but didn't escape the backslash correctly maybe? Or it got interpreted as a real newline?
content = content.replace('                b"q\n"', '                b"q\\n"')
content = content.replace('                + _number(left) + b" " + _number(bottom) + b" cm\n"', '                + _number(left) + b" " + _number(bottom) + b" cm\\n"')
content = content.replace('                + b"/Im0 Do\nQ\n"', '                + b"/Im0 Do\\nQ\\n"')

with open('src/pdf_size_fit/color_fit.py', 'w') as f:
    f.write(content)
