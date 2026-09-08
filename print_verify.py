with open('src/pdf_size_fit/color_fit.py', 'r') as f:
    content = f.read()

verify = content.split("def _verify_candidate")[1].split("def ")[0]
print(verify)
