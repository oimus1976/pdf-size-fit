with open('src/pdf_size_fit/color_fit.py', 'r') as f:
    content = f.read()

# Let's check where the pdfium output verification code is.
print("Does _verify_candidate have pdfium?")
if "pdfium" in content.split("def _verify_candidate")[1].split("def ")[0]:
    print("Yes!")
else:
    print("NO!!!")
