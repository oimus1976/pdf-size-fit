import re

with open('src/pdf_size_fit/color_fit.py', 'r') as f:
    content = f.read()

# I messed up the order and arguments. Let's strictly replace `_result` so we don't pass bits_per_pixel or compression anymore.
content = re.sub(
    r'        return ColorFitResult\(\n            status=status,\n            input_path=str\(input_path\),\n            output_path=str\(output_path\) if output_path is not None else None,\n            input_size_bytes=input_size,\n            output_size_bytes=output_size,\n            target_bytes=target_bytes,\n            route=Route\.VECTOR_COLOR\.value,\n            dpi=FIXED_COLOR_DPI,\n            bits_per_pixel=1,\n            compression="CCITT Group 4",\n            page_count=page_count,\n            reasons=reasons,\n        \)',
    r'''        return ColorFitResult(
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
        )''',
    content
)

# And if it was not exactly that string:
content = content.replace(
    '            bits_per_pixel=1,\n            compression="CCITT Group 4",',
    '            jpeg_quality=jpeg_quality if status is ColorFitStatus.FITTED else None,'
)

with open('src/pdf_size_fit/color_fit.py', 'w') as f:
    f.write(content)
