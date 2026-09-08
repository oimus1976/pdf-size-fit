import re

with open('src/pdf_size_fit/color_fit.py', 'r') as f:
    content = f.read()

# 1. Add pdfium verification to _verify_candidate
content = re.sub(
    r'def _verify_candidate\(input_path: Path, candidate_path: Path\) -> None:\n    source = PdfReader\(str\(input_path\)\)\n    candidate = PdfReader\(str\(candidate_path\)\)',
    r'''def _verify_candidate(input_path: Path, candidate_path: Path) -> None:
    import pypdfium2 as pdfium
    source = PdfReader(str(input_path))
    candidate = PdfReader(str(candidate_path))''',
    content,
    flags=re.DOTALL
)

# Replace the body to include pdfium rendering
content = re.sub(
    r'            raise RuntimeError\(f"candidate page \{index\} is not RGB JPEG"\)',
    r'''            raise RuntimeError(f"candidate page {index} is not RGB JPEG")

    pdf = pdfium.PdfDocument(str(candidate_path))
    try:
        if len(pdf) != len(source.pages):
            raise RuntimeError("candidate page count disagrees with pypdf source")
        for i in range(len(pdf)):
            page = pdf[i]
            bitmap = None
            try:
                bitmap = page.render(scale=1.0)
            except Exception as e:
                raise RuntimeError(f"candidate page {i + 1} failed PDFium rendering: {e}")
            finally:
                if bitmap is not None:
                    bitmap.close()
                page.close()
    finally:
        pdf.close()''',
    content,
    flags=re.DOTALL
)

# 5. Result explicitly records searchable text loss
content = content.replace(
    '    jpeg_quality: int | None = None',
    '    jpeg_quality: int | None = None\n    searchable_text_semantics_lost: bool | None = None'
)
content = content.replace(
    '        "jpeg_quality": self.jpeg_quality,',
    '        "jpeg_quality": self.jpeg_quality,\n        "searchable_text_semantics_lost": self.searchable_text_semantics_lost,'
)

content = re.sub(
    r'def _result\(\n    status: ColorFitStatus,\n    input_path: Path,\n    \*,\n    input_size: int,\n    target_bytes: int,\n    page_count: int,\n    reasons: tuple\[str, \.\.\.\],\n    output_path: Path \| None = None,\n    output_size: int \| None = None,\n    jpeg_quality: int \| None = None,\n\) -> ColorFitResult:',
    r'''def _result(
    status: ColorFitStatus,
    input_path: Path,
    *,
    input_size: int,
    target_bytes: int,
    page_count: int,
    reasons: tuple[str, ...],
    output_path: Path | None = None,
    output_size: int | None = None,
    jpeg_quality: int | None = None,
    searchable_text_semantics_lost: bool | None = None,
) -> ColorFitResult:''',
    content,
    flags=re.DOTALL
)

content = content.replace(
    '        jpeg_quality=jpeg_quality if status is ColorFitStatus.FITTED else None,\n    )',
    '        jpeg_quality=jpeg_quality if status is ColorFitStatus.FITTED else None,\n        searchable_text_semantics_lost=searchable_text_semantics_lost,\n    )'
)

# Modify the call to _result in fit_color_vector_pdf
content = content.replace(
    '    if small_searchable_text_rasterized:\n        reasons.append(\n            "a small selectable/searchable text layer was rasterized within both "\n            "parsers\' provisional bounds by explicit opt-in; selectable/searchable "\n            "and search/copy semantics were lost"\n        )\n    reasons.append(\n        "whole-page rasterization is destructive and does not preserve selectable text or vector scalability"\n    )\n\n    return _result(\n        ColorFitStatus.FITTED,\n        input_path,\n        input_size=input_size,\n        target_bytes=target_bytes,\n        page_count=len(page_specs),\n        output_path=output_path,\n        output_size=output_size,\n        jpeg_quality=jpeg_quality,\n        reasons=tuple(reasons),\n    )',
    r'''    if small_searchable_text_rasterized:
        reasons.append(
            "a small selectable/searchable text layer was rasterized within both "
            "parsers' provisional bounds by explicit opt-in; selectable/searchable "
            "and search/copy semantics were lost"
        )
    reasons.append(
        "whole-page rasterization is destructive and does not preserve selectable text or vector scalability"
    )

    return _result(
        ColorFitStatus.FITTED,
        input_path,
        input_size=input_size,
        target_bytes=target_bytes,
        page_count=len(page_specs),
        output_path=output_path,
        output_size=output_size,
        jpeg_quality=jpeg_quality,
        searchable_text_semantics_lost=small_searchable_text_rasterized if small_searchable_text_rasterized else False,
        reasons=tuple(reasons),
    )'''
)

with open('src/pdf_size_fit/color_fit.py', 'w') as f:
    f.write(content)
