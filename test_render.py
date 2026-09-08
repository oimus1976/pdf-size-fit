with open('tests/test_color_fit.py', 'r') as f:
    content = f.read()

import re
# Oh! The problem is that the PDF is rendered 1 time per page during `_build_candidate`. Since the source has 1 page, `_build_candidate` renders it once.
# Then `_verify_candidate` SHOULD render it again for the output candidate.
# BUT `_verify_candidate` actually DOES NOT CALL `.render()` YET!
# The issue reviewer SAID: "The current color_fit._verify_candidate() verifies pypdf reopen/page structure and the RGB JPEG XObject dictionary, but it does not open the accepted candidate/output with PDFium and render every page."
# I THOUGHT I FIXED IT WITH `fix_pdfium_verify.py` BUT I DID A `git reset --hard` EARLIER!
print("Ah! It's not in the file!")
