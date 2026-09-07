import re

with open('src/pdf_size_fit/color_fit.py', 'r') as f:
    content = f.read()

# I am completely lost on why it still has `bits_per_pixel=1, compression="CCITT Group 4"`
# I will just write a python script that completely replaces the `_result` function block.
func = '''def _result(
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
) -> ColorFitResult:
    return ColorFitResult(
        status=status,
        input_path=str(input_path),
        output_path=str(output_path) if output_path is not None else None,
        input_size_bytes=input_size,
        output_size_bytes=output_size,
        target_bytes=target_bytes,
        route=Route.VECTOR_COLOR.value,
        page_count=page_count,
        reasons=reasons,
        dpi=FIXED_COLOR_DPI if status is ColorFitStatus.FITTED else None,
        jpeg_quality=jpeg_quality if status is ColorFitStatus.FITTED else None,
    )'''

# find the definition of _result and replace it completely until the next def
content = re.sub(r'def _result\(.*?\) -> ColorFitResult:.*?(?=\ndef )', func + '\n\n', content, flags=re.DOTALL)

with open('src/pdf_size_fit/color_fit.py', 'w') as f:
    f.write(content)
