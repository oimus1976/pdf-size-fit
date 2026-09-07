import os
import shutil
import re

# 1. Create color_fit.py from monochrome_fit.py
shutil.copy('src/pdf_size_fit/monochrome_fit.py', 'src/pdf_size_fit/color_fit.py')
shutil.copy('src/pdf_size_fit/monochrome_cli.py', 'src/pdf_size_fit/color_cli.py')
shutil.copy('tests/test_monochrome_fit.py', 'tests/test_color_fit.py')

with open('src/pdf_size_fit/color_fit.py', 'r') as f:
    content = f.read()

content = content.replace('MonochromeFitStatus', 'ColorFitStatus')
content = content.replace('MonochromeFitResult', 'ColorFitResult')
content = content.replace('fit_monochrome_vector_pdf', 'fit_color_vector_pdf')
content = content.replace('Route.VECTOR_MONOCHROME', 'Route.VECTOR_COLOR')
content = content.replace('FIXED_DPI', 'FIXED_COLOR_DPI')
content = content.replace('FIXED_COLOR_DPI = 300', 'FIXED_COLOR_DPI = 200')
content = content.replace('from PIL import Image, ImageChops, ImageFilter', 'from PIL import Image')

content = re.sub(
    r'from pypdf.generic import \(\n    ArrayObject,\n    BooleanObject,\n    DecodedStreamObject,\n    DictionaryObject,\n    IndirectObject,\n    NameObject,\n    NumberObject,\n    RectangleObject,\n    StreamObject,\n\)',
    r'from pypdf.generic import (\n    ArrayObject,\n    BooleanObject,\n    DecodedStreamObject,\n    DictionaryObject,\n    IndirectObject,\n    NameObject,\n    NumberObject,\n    RectangleObject,\n    StreamObject,\n)',
    content,
    flags=re.DOTALL
)

# Remove unused midtone and chroma functions
content = re.sub(r'def _has_persistent_unsupported_midtone\(.*?\n\n\n', '\n', content, flags=re.DOTALL)
content = re.sub(r'def _has_material_chroma\(.*?\n\n\n', '\n', content, flags=re.DOTALL)
content = re.sub(r'def _bilevel_suitability_refusal\(.*?\n\n\n', '\n', content, flags=re.DOTALL)

# Update Result structure
content = content.replace(
    '''class ColorFitResult:
    status: ColorFitStatus
    input_path: str
    output_path: str | None
    input_size_bytes: int
    output_size_bytes: int | None
    target_bytes: int
    route: str
    dpi: int
    bits_per_pixel: int
    compression: str
    page_count: int
    reasons: tuple[str, ...]''',
    '''class ColorFitResult:
    status: ColorFitStatus
    input_path: str
    output_path: str | None
    input_size_bytes: int
    output_size_bytes: int | None
    target_bytes: int
    route: str
    dpi: int | None = None
    jpeg_quality: int | None = None
    page_count: int
    reasons: tuple[str, ...]'''
)

content = content.replace(
    '        "bits_per_pixel": self.bits_per_pixel,\n        "compression": self.compression,',
    '        "jpeg_quality": self.jpeg_quality,'
)

content = re.sub(
    r'def _result\(.*?\n\) -> ColorFitResult:',
    '''def _result(
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
) -> ColorFitResult:''',
    content,
    flags=re.DOTALL
)

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
            dpi=FIXED_COLOR_DPI if status is ColorFitStatus.FITTED else None,
            jpeg_quality=jpeg_quality if status is ColorFitStatus.FITTED else None,
            page_count=page_count,
            reasons=reasons,
        )''',
    content
)

# Fix _destructive_content_refusal
content = re.sub(
    r'    if pages_with_text and not allow_small_searchable_text_rasterization:.*?    return \(\n        _bilevel_suitability_refusal\(input_path, page_specs\),\n        bool\(pages_with_text and allow_small_searchable_text_rasterization\),\n    \)',
    r'''    if pages_with_text and not allow_small_searchable_text_rasterization:
        return (
            (
                f"page {pages_with_text[0]} contains selectable/searchable text that "
                "at least one of pypdf or PDFium detected and whole-page "
                "rasterization would discard"
            ),
            False,
        )

    if allow_small_searchable_text_rasterization:
        for parser_name, metrics in (
            ("pypdf", pypdf_metrics),
            ("PDFium", pdfium_metrics),
        ):
            for index, (non_whitespace_chars, _) in enumerate(metrics, start=1):
                if non_whitespace_chars > MAX_SEARCHABLE_TEXT_CHARS_PER_PAGE:
                    return (
                        f"page {index} {parser_name} normalized text metrics contain "
                        f"{non_whitespace_chars} non-whitespace characters, above "
                        "the explicit opt-in limit of "
                        f"{MAX_SEARCHABLE_TEXT_CHARS_PER_PAGE}",
                        False,
                    )
            for index, (_, non_empty_lines) in enumerate(metrics, start=1):
                if non_empty_lines > MAX_SEARCHABLE_TEXT_LINES_PER_PAGE:
                    return (
                        f"page {index} {parser_name} normalized text metrics contain "
                        f"{non_empty_lines} non-empty lines, above the explicit "
                        f"opt-in limit of {MAX_SEARCHABLE_TEXT_LINES_PER_PAGE}",
                        False,
                    )
            document_chars = sum(non_whitespace for non_whitespace, _ in metrics)
            if document_chars > MAX_SEARCHABLE_TEXT_CHARS_PER_DOCUMENT:
                return (
                    f"document {parser_name} normalized text metrics contain "
                    f"{document_chars} non-whitespace characters, above the "
                    "explicit opt-in limit of "
                    f"{MAX_SEARCHABLE_TEXT_CHARS_PER_DOCUMENT}",
                    False,
                )

        for index, (pypdf_metric, pdfium_metric) in enumerate(
            zip(pypdf_metrics, pdfium_metrics), start=1
        ):
            if pypdf_metric != pdfium_metric:
                return (
                    f"page {index} normalized text metrics disagree between pypdf "
                    "and PDFium",
                    False,
                )

    return None, bool(pages_with_text and allow_small_searchable_text_rasterization)''',
    content,
    flags=re.DOTALL
)

# _single_ccitt_image -> _single_jpeg_image
content = re.sub(
    r'def _single_ccitt_image\(image: Image\.Image, writer: PdfWriter\) -> IndirectObject:.*?return writer\._add_object\(image_object\)',
    r'''def _single_jpeg_image(image: Image.Image, writer: PdfWriter, jpeg_quality: int) -> IndirectObject:
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=jpeg_quality, optimize=True)
    buffer.seek(0)

    stream = StreamObject()
    stream._data = buffer.read()

    image_dict = DictionaryObject({
        NameObject("/Type"): NameObject("/XObject"),
        NameObject("/Subtype"): NameObject("/Image"),
        NameObject("/Width"): NumberObject(image.width),
        NameObject("/Height"): NumberObject(image.height),
        NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
        NameObject("/BitsPerComponent"): NumberObject(8),
        NameObject("/Filter"): NameObject("/DCTDecode"),
        NameObject("/Length"): NumberObject(len(stream._data))
    })

    stream.update(image_dict)
    return writer._add_object(stream)''',
    content,
    flags=re.DOTALL
)

# update _build_candidate
content = re.sub(
    r'def _build_candidate\([^)]+\) -> None:.*?finally:\n        pdf\.close\(\)',
    r'''def _build_candidate(
    input_path: Path,
    candidate_path: Path,
    page_specs: tuple[_PageSpec, ...],
    jpeg_quality: int,
) -> None:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(input_path))
    writer = PdfWriter()
    scale = FIXED_COLOR_DPI / 72.0
    try:
        if len(pdf) != len(page_specs):
            raise RuntimeError("PDFium and pypdf disagree on the source page count")
        for index, spec in enumerate(page_specs):
            source_page = pdf[index]
            bitmap = None
            try:
                normalized_rotation = spec.rotation % 360
                if source_page.get_rotation() != normalized_rotation:
                    raise RuntimeError(f"page {index + 1} rotation differs between PDF readers")
                bitmap = source_page.render(
                    scale=scale,
                    rotation=(-normalized_rotation) % 360,
                    grayscale=False,
                    draw_annots=False,
                )
                rgb_image = bitmap.to_pil().convert("RGB")
            finally:
                if bitmap is not None:
                    bitmap.close()
                source_page.close()

            expected_size = (ceil(spec.width * scale), ceil(spec.height * scale))
            _require_render_size_within_rounding_tolerance(
                rgb_image.size,
                expected_size,
                index + 1,
            )

            image_ref = _single_jpeg_image(rgb_image, writer, jpeg_quality)
            page = writer.add_blank_page(width=spec.width, height=spec.height)
            page[NameObject("/MediaBox")] = RectangleObject(spec.mediabox)
            page[NameObject("/Rotate")] = NumberObject(spec.rotation)
            page[NameObject("/Resources")] = DictionaryObject(
                {
                    NameObject("/XObject"): DictionaryObject(
                        {NameObject("/Im0"): image_ref}
                    )
                }
            )
            left, bottom, _, _ = spec.mediabox
            content = DecodedStreamObject()
            content.set_data(
                b"q\n"
                + _number(spec.width) + b" 0 0 " + _number(spec.height) + b" "
                + _number(left) + b" " + _number(bottom) + b" cm\n"
                + b"/Im0 Do\nQ\n"
            )
            page.replace_contents(content)
    finally:
        pdf.close()''',
    content,
    flags=re.DOTALL
)

# Replace verify checks in _verify_candidate
content = re.sub(
    r'        if \(\n            filters != \("/CCITTFaxDecode",\)\n            or image_object\.get\("/BitsPerComponent"\) != 1\n            or image_object\.get\("/ColorSpace"\) != "/DeviceGray"\n            or not isinstance\(decode_params, DictionaryObject\)\n            or decode_params\.get\("/K"\) != -1\n            or decode_params\.get\("/BlackIs1"\) != BooleanObject\(True\)\n        \):\n            raise RuntimeError\(f"candidate page \{index\} is not 1-bit CCITT Group 4"\)',
    r'''        if (
            filters != ("/DCTDecode",)
            or image_object.get("/BitsPerComponent") != 8
            or image_object.get("/ColorSpace") != "/DeviceRGB"
        ):
            raise RuntimeError(f"candidate page {index} is not RGB JPEG")''',
    content,
    flags=re.DOTALL
)

# Update fit_color_vector_pdf signature and body
content = re.sub(
    r'def fit_color_vector_pdf\([^)]+\) -> ColorFitResult:',
    r'''def fit_color_vector_pdf(
    input_path: str | Path,
    output_path: str | Path,
    *,
    target_bytes: int = 10_000_000,
    dpi: int = FIXED_COLOR_DPI,
    jpeg_quality: int = 90,
    allow_small_searchable_text_rasterization: bool = False,
) -> ColorFitResult:''',
    content,
    flags=re.DOTALL
)

content = re.sub(
    r'    if dpi != FIXED_COLOR_DPI:\n        raise ValueError\("dpi must be exactly 300; DPI search is not validated"\)',
    r'''    if dpi != FIXED_COLOR_DPI:
        raise ValueError("dpi must be exactly 200; DPI search is not validated")
    if jpeg_quality != 90:
        raise ValueError("jpeg_quality must be exactly 90; search is not validated")''',
    content,
    flags=re.DOTALL
)

content = re.sub(
    r'            candidate = Path\(temp_dir\) / "candidate-300dpi-g4.pdf"\n            _build_candidate\(input_path, candidate, page_specs\)',
    r'''            candidate = Path(temp_dir) / "candidate-200dpi-q90.pdf"
            _build_candidate(input_path, candidate, page_specs, jpeg_quality)''',
    content,
    flags=re.DOTALL
)

content = re.sub(
    r'f"fixed 300 dpi candidate is \{candidate_size\} bytes',
    r'f"fixed 200 dpi / q90 candidate is {candidate_size} bytes',
    content,
    flags=re.DOTALL
)

content = re.sub(
    r'"all pages were rendered by PDFium at fixed 300 dpi and encoded as 1-bit CCITT Group 4",',
    r'"all pages were rendered by PDFium at fixed 200 dpi and encoded as RGB JPEG",',
    content,
    flags=re.DOTALL
)
content = content.replace(
    '        output_size=output_size,\n        reasons=tuple(reasons),\n    )',
    '        output_size=output_size,\n        jpeg_quality=jpeg_quality,\n        reasons=tuple(reasons),\n    )'
)
content = content.replace(
    'if diagnosis.route is not Route.VECTOR_MONOCHROME:',
    'if diagnosis.route is not Route.VECTOR_COLOR:'
)

content = content.replace(
    'f"diagnosis proposed route {diagnosis.route.value!r}, not \'vector-monochrome\'",',
    'f"diagnosis proposed route {diagnosis.route.value!r}, not \'vector-color\'",'
)

content = content.replace(
    '"diagnosis selected the vector-monochrome route for the requested target",',
    '"diagnosis selected the vector-color route for the requested target",'
)

with open('src/pdf_size_fit/color_fit.py', 'w') as f:
    f.write(content)


# 2. Update __init__ and fit.py
with open('src/pdf_size_fit/__init__.py', 'r') as f:
    content = f.read()

content = content.replace(
    'from .monochrome_fit import (',
    '''from .color_fit import (
    ColorFitResult,
    ColorFitStatus,
    fit_color_vector_pdf,
)
from .monochrome_fit import ('''
)
content = content.replace(
    '    "fit_image_heavy_pdf",\n',
    '''    "fit_image_heavy_pdf",
    "ColorFitResult",
    "ColorFitStatus",
    "fit_color_vector_pdf",\n'''
)
with open('src/pdf_size_fit/__init__.py', 'w') as f:
    f.write(content)


with open('src/pdf_size_fit/fit.py', 'r') as f:
    content = f.read()

content = content.replace(
    'from .image_fit import ImageFitResult, ImageFitStatus, fit_image_heavy_pdf',
    '''from .color_fit import (
    FIXED_COLOR_DPI,
    ColorFitResult,
    ColorFitStatus,
    fit_color_vector_pdf,
)
from .image_fit import ImageFitResult, ImageFitStatus, fit_image_heavy_pdf'''
)
content = content.replace(
    'RouteResult = ImageFitResult | MonochromeFitResult',
    'RouteResult = ImageFitResult | MonochromeFitResult | ColorFitResult'
)
content = content.replace(
    '        and result.status is MonochromeFitStatus.FITTED\n    ):',
    '''        and result.status is MonochromeFitStatus.FITTED
    ) or (
        isinstance(result, ColorFitResult)
        and result.status is ColorFitStatus.FITTED
    ):'''
)
content = content.replace(
    '        and result.status is MonochromeFitStatus.SKIP\n    ):',
    '''        and result.status is MonochromeFitStatus.SKIP
    ) or (
        isinstance(result, ColorFitResult)
        and result.status is ColorFitStatus.SKIP
    ):'''
)

new_route_handling = '''    if diagnosis.route is Route.VECTOR_MONOCHROME:
        route_result = fit_monochrome_vector_pdf(
            input_path,
            output_path,
            target_bytes=target_bytes,
            dpi=FIXED_DPI,
            allow_small_searchable_text_rasterization=(
                allow_small_searchable_text_rasterization
            ),
        )
        return _normalize_route_result(diagnosis, route_result)

    if diagnosis.route is Route.VECTOR_COLOR:
        route_result = fit_color_vector_pdf(
            input_path,
            output_path,
            target_bytes=target_bytes,
            dpi=FIXED_COLOR_DPI,
            jpeg_quality=90,
            allow_small_searchable_text_rasterization=(
                allow_small_searchable_text_rasterization
            ),
        )
        return _normalize_route_result(diagnosis, route_result)'''

content = content.replace(
    '''    if diagnosis.route is Route.VECTOR_MONOCHROME:
        route_result = fit_monochrome_vector_pdf(
            input_path,
            output_path,
            target_bytes=target_bytes,
            dpi=FIXED_DPI,
            allow_small_searchable_text_rasterization=(
                allow_small_searchable_text_rasterization
            ),
        )
        return _normalize_route_result(diagnosis, route_result)''',
    new_route_handling
)

with open('src/pdf_size_fit/fit.py', 'w') as f:
    f.write(content)

# 3. Update color_cli
with open('src/pdf_size_fit/color_cli.py', 'r') as f:
    content = f.read()

content = content.replace('monochrome_fit', 'color_fit')
content = content.replace('Monochrome vector PDF', 'Color vector PDF')
content = content.replace('fit_monochrome_vector_pdf', 'fit_color_vector_pdf')
content = content.replace('300', '200')
content = content.replace('MonochromeFitResult', 'ColorFitResult')
content = content.replace('MonochromeFitStatus', 'ColorFitStatus')

content = re.sub(
    r'parser\.add_argument\([^)]+"--dpi"[^)]+\)',
    r'''parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="Fixed whole-page rasterization DPI (must be 200)",
    )
    parser.add_argument(
        "--jpeg-quality",
        type=int,
        default=90,
        help="Fixed JPEG encoding quality (must be 90)",
    )''',
    content,
    flags=re.DOTALL
)

content = re.sub(
    r'dpi=args\.dpi,',
    r'dpi=args.dpi,\n        jpeg_quality=args.jpeg_quality,',
    content
)
content = content.replace('monochrome', 'color')
content = content.replace(
    'from .color_fit import ColorFitResult, ColorFitStatus, fit_color_vector_pdf',
    'from .color_fit import (\n    ColorFitResult,\n    ColorFitStatus,\n    fit_color_vector_pdf,\n)'
)

with open('src/pdf_size_fit/color_cli.py', 'w') as f:
    f.write(content)

# Update cli.py
with open('src/pdf_size_fit/cli.py', 'r') as f:
    content = f.read()
content = content.replace(
    'from .fit_cli import main as fit_main',
    'from .fit_cli import main as fit_main\nfrom .color_cli import main as color_main'
)
with open('src/pdf_size_fit/cli.py', 'w') as f:
    f.write(content)

# Update pyproject.toml
with open('pyproject.toml', 'r') as f:
    content = f.read()
content = content.replace(
    'pdf-size-fit-monochrome = "pdf_size_fit.monochrome_cli:main"',
    'pdf-size-fit-monochrome = "pdf_size_fit.monochrome_cli:main"\npdf-size-fit-color = "pdf_size_fit.color_cli:main"'
)
with open('pyproject.toml', 'w') as f:
    f.write(content)


# 4. Create and Fix test_color_fit.py
with open('tests/test_color_fit.py', 'r') as f:
    content = f.read()

content = content.replace('monochrome_fit', 'color_fit')
content = content.replace('MonochromeFitStatus', 'ColorFitStatus')
content = content.replace('fit_monochrome_vector_pdf', 'fit_color_vector_pdf')
content = content.replace('Route.VECTOR_MONOCHROME', 'Route.VECTOR_COLOR')
content = content.replace('test_monochrome_fit_', 'test_color_fit_')
content = content.replace('MonochromeFitResult', 'ColorFitResult')
content = content.replace('test_fit_monochrome', 'test_fit_color')
content = content.replace('dpi=300', 'dpi=200, jpeg_quality=90')
content = content.replace('dpi=150', 'dpi=150')
content = content.replace('fixed 300 dpi', 'fixed 200 dpi')

content = re.sub(r'def test_color_fit_refuses_persistent_unsupported_midtone.*?def test_color_fit_accepts_sub_3_pixel_unsupported_midtone_detail', '', content, flags=re.DOTALL)
content = re.sub(r'def test_color_fit_refuses_material_chroma.*?(?=def test_color_fit)', '', content, flags=re.DOTALL)
content = re.sub(r'def test_fit_refuses_material_grayscale_midtone_content.*?(?=def test_candidate_rendering_remains_grayscale_then_pillow_one_bit)', '', content, flags=re.DOTALL)
content = re.sub(r'def test_candidate_rendering_remains_grayscale_then_pillow_one_bit.*?(?=def test_target_not_met_does_not_search_dpi_or_write_output)', '', content, flags=re.DOTALL)
content = re.sub(r'def test_300dpi_chroma_gate_refuses_saturated_features.*?(?=def test_300dpi_chroma_inspection_failure_fails_closed)', '', content, flags=re.DOTALL)
content = re.sub(r'def test_300dpi_chroma_inspection_failure_fails_closed.*?(?=def test_bilevel_render_failure_fails_closed)', '', content, flags=re.DOTALL)
content = re.sub(r'def test_bilevel_render_failure_fails_closed.*?(?=def test_target_not_met_does_not_search_dpi_or_write_output)', '', content, flags=re.DOTALL)

content = content.replace('test_successful_fixed_200_dpi_color_fit_is_1bit_ccitt_g4', 'test_successful_fixed_200_dpi_color_fit_is_rgb_jpeg')
content = content.replace('def test_non_300_dpi_is_rejected', 'def test_non_200_dpi_is_rejected')

content = re.sub(
    r'            or decode_params\.get\("/K"\) != -1\n            or decode_params\.get\("/BlackIs1"\) != getattr\(decode_params, "_fake", True\) # Wait I removed BooleanObject earlier, let me just replace the whole block\n        \):\n            raise RuntimeError\(f"candidate page \{index\} is not 1-bit CCITT Group 4"\)',
    r'''        ):
            raise RuntimeError(f"candidate page {index} is not RGB JPEG")''',
    content,
    flags=re.DOTALL
)
content = re.sub(
    r'        if \(\n            filters != \("/CCITTFaxDecode",\)\n            or image_object\.get\("/BitsPerComponent"\) != 1\n            or image_object\.get\("/ColorSpace"\) != "/DeviceGray"\n            or not isinstance\(decode_params, DictionaryObject\)\n            or decode_params\.get\("/K"\) != -1\n            or decode_params\.get\("/BlackIs1"\) != BooleanObject\(True\)\n        \):\n            raise RuntimeError\(f"candidate page \{index\} is not 1-bit CCITT Group 4"\)',
    r'''        if (
            filters != ("/DCTDecode",)
            or image_object.get("/BitsPerComponent") != 8
            or image_object.get("/ColorSpace") != "/DeviceRGB"
        ):
            raise RuntimeError(f"candidate page {index} is not RGB JPEG")''',
    content,
    flags=re.DOTALL
)

content = re.sub(r'assert "fixed 200 dpi candidate is " in result\.reasons\[0\]', 'assert "fixed 200 dpi / q90 candidate is " in result.reasons[0]', content)
content = re.sub(r'assert "DPI was not reduced or searched" in result\.reasons\[1\]', 'assert "DPI was not reduced or searched" in result.reasons[1]', content)

content = content.replace('assert result.dpi == 300', 'assert result.dpi == 200')

content = content.replace(
    '_force_vector_monochrome_diagnosis(monkeypatch)',
    '_force_vector_color_diagnosis(monkeypatch)'
)

content = content.replace('_generate_vector_pdf(source)', '_generate_vector_pdf(source, color=True)')
content = content.replace('_generate_vector_pdf(source, page_specs=((595.0, 842.0, 0), (420.0, 595.0, 90)))', '_generate_vector_pdf(source, color=True, page_specs=((595.0, 842.0, 0), (420.0, 595.0, 90)))')
content = content.replace('_generate_vector_pdf(\n        source,\n        page_specs=((595.0, 842.0, 0), (420.0, 595.0, 90)),\n    )', '_generate_vector_pdf(\n        source,\n        color=True,\n        page_specs=((595.0, 842.0, 0), (420.0, 595.0, 90)),\n    )')

content = content.replace(
    'def _force_vector_monochrome_diagnosis(',
    'def _force_vector_color_diagnosis('
)

content = content.replace('assert result.bits_per_pixel == 1', 'assert result.jpeg_quality == 90')
content = content.replace('assert result.compression == "CCITT Group 4"\n', '')
content = content.replace('assert list(filters) == ["/CCITTFaxDecode"]', 'assert filters == "/DCTDecode"')
content = content.replace('assert image_object["/BitsPerComponent"] == 1', 'assert image_object["/BitsPerComponent"] == 8')
content = content.replace('assert image_object["/ColorSpace"] == "/DeviceGray"', 'assert image_object["/ColorSpace"] == "/DeviceRGB"')
content = re.sub(r'    decode_params = image_object\["/DecodeParms"\]\[0\].*?assert decode_params\["/K"\] == -1', '', content, flags=re.DOTALL)
content = re.sub(r'    decode_params = image_object\["/DecodeParms"\].*?assert decode_params\["/K"\] == -1', '', content, flags=re.DOTALL)
content = re.sub(r'    decode_params = image_object\["/DecodeParms"\].*', '', content, flags=re.DOTALL)
content = re.sub(r'    assert bool\(decode_params\["/BlackIs1"\]\)', '', content)

content = re.sub(
    r'def _generate_vector_text_pdf\(.*?path: Path,.*?pages: tuple\[tuple\[str, \.\.\.\], \.\.\.\],.*?\).*?stream\.set_data\(b"0 G 0\.5 w\\n" \+ b""\.join\(drawing\)\)',
    r'''def _generate_vector_text_pdf(
    path: Path,
    pages: tuple[tuple[str, ...], ...],
    color: bool = True,
    repeats: int = 1,
) -> None:
    writer = PdfWriter()
    stroke = b"0.8 0.1 0.1 RG\n" if color else b"0 G\n"
    for text_lines in pages:
        page = writer.add_blank_page(width=595.0, height=842.0)
        drawing = []
        for line in text_lines:
            drawing.append(b"40 40 m 540 790 l S\n" * repeats)
            drawing.append(b"BT /F1 12 Tf 100 100 Td (" + line.encode("latin-1") + b") Tj ET\n")
        stream = DecodedStreamObject()
        stream.set_data(stroke + b"0.5 w\n" + b"".join(drawing))''',
    content,
    flags=re.DOTALL
)
content = re.sub(r'def _generate_vector_text_pdf_monochrome\(.*?stream\.set_data\(b"0 G 0\.5 w\\n" \+ b""\.join\(drawing\)\)',
                 r'''def _generate_vector_text_pdf(
    path: Path,
    pages: tuple[tuple[str, ...], ...],
    color: bool = True,
    repeats: int = 1,
) -> None:
    writer = PdfWriter()
    stroke = b"0.8 0.1 0.1 RG\n" if color else b"0 G\n"
    for text_lines in pages:
        page = writer.add_blank_page(width=595.0, height=842.0)
        drawing = []
        for line in text_lines:
            drawing.append(b"40 40 m 540 790 l S\n" * repeats)
            drawing.append(b"BT /F1 12 Tf 100 100 Td (" + line.encode("latin-1") + b") Tj ET\n")
        stream = DecodedStreamObject()
        stream.set_data(stroke + b"0.5 w\n" + b"".join(drawing))''',
                 content, flags=re.DOTALL)
content = content.replace('_generate_vector_text_pdf_monochrome', '_generate_vector_text_pdf')
content = content.replace(
    '_generate_vector_pdf(source, color=True)\n\n    result = fit_color_vector_pdf(source, output, target_bytes=_fit_target(source))\n\n    assert result.status is ColorFitStatus.ROUTE_MISMATCH',
    '_generate_vector_pdf(source, color=False)\n\n    result = fit_color_vector_pdf(source, output, target_bytes=_fit_target(source))\n\n    assert result.status is ColorFitStatus.ROUTE_MISMATCH'
)

content = content.replace('match="exactly 300"', 'match="exactly 200"')
content = content.replace('test_fit_requires_existing_vector_monochrome_diagnosis', 'test_fit_requires_existing_vector_color_diagnosis')
content = content.replace('not \'vector-monochrome\'', 'not \'vector-color\'')
content = content.replace('diagnosis.route = Route.VECTOR_MONOCHROME', 'diagnosis.route = Route.VECTOR_COLOR')
content = re.sub(r'import pypdfium2\n', '', content)
content = re.sub(r'        # Note: the pdf must actually result in Route\.VECTOR_COLOR if the patch fails\. Wait, let us ensure _force_vector_color_diagnosis forces VECTOR_COLOR properly\n', '', content)
content = content.replace('from PIL import Image\n', '')

content = content.replace(
    '''def test_text_opt_in_fits_small_repeated_searchable_layer(tmp_path: Path) -> None:
    source = tmp_path / "small-searchable-layer.pdf"
    output = tmp_path / "output.pdf"
    _generate_vector_text_pdf(source, (("12345678",), ("12345678",)))

    result = fit_color_vector_pdf(
        source,
        output,
        target_bytes=_fit_target(source),
        allow_small_searchable_text_rasterization=True,
    )''',
    '''def test_text_opt_in_fits_small_repeated_searchable_layer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "small-searchable-layer.pdf"
    output = tmp_path / "output.pdf"
    _generate_vector_text_pdf(source, (("12345678",), ("12345678",)), color=True, repeats=8000)
    _force_vector_color_diagnosis(monkeypatch)

    result = fit_color_vector_pdf(
        source,
        output,
        target_bytes=_fit_target(source),
        allow_small_searchable_text_rasterization=True,
    )'''
)

content = content.replace(
    '''def test_text_opt_in_refuses_more_than_one_non_empty_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "too-many-lines.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_text_pdf(source, (("a", "b"),))
    monkeypatch.setattr(
        color_fit,
        "_pdfium_text_metrics",
        lambda *_args: (((0, 0),), None),
    )

    result = fit_color_vector_pdf(
        source,
        output,
        target_bytes=1,
        allow_small_searchable_text_rasterization=True,
    )

    assert result.status is ColorFitStatus.UNSUPPORTED_DOCUMENT
    assert "page 1 pypdf" in result.reasons[0]''',
    '''def test_text_opt_in_refuses_more_than_one_non_empty_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "too-many-lines.pdf"
    output = tmp_path / "should-not-exist.pdf"
    _generate_vector_text_pdf(source, (("a", "b"),), color=True, repeats=1)
    _force_vector_color_diagnosis(monkeypatch)
    monkeypatch.setattr(
        color_fit,
        "_pdfium_text_metrics",
        lambda *_args: (((2, 2),), None),
    )
    monkeypatch.setattr(
        color_fit,
        "_pypdf_text_metrics",
        lambda *_args: (((2, 2),), None),
    )

    result = fit_color_vector_pdf(
        source,
        output,
        target_bytes=1,
        allow_small_searchable_text_rasterization=True,
    )

    assert result.status is ColorFitStatus.UNSUPPORTED_DOCUMENT
    assert "page 1 pypdf" in result.reasons[0]'''
)

with open('tests/test_color_fit.py', 'w') as f:
    f.write(content)

# Update test_fit.py
with open('tests/test_fit.py', 'r') as f:
    content = f.read()

content = content.replace(
    '@pytest.mark.parametrize("route", [Route.VECTOR_COLOR, Route.UNCLASSIFIED])',
    '@pytest.mark.parametrize("route", [Route.UNCLASSIFIED])'
)

new_test = '''def test_vector_color_dispatches_to_color_fit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input.pdf"
    output = tmp_path / "output.pdf"
    source.write_bytes(b"mock pdf")
    diagnosis = _diagnosis(source, Route.VECTOR_COLOR)
    monkeypatch.setattr("pdf_size_fit.fit.diagnose_pdf", lambda *args, **kwargs: diagnosis)

    called = False

    def mock_fit(*args: object, **kwargs: object) -> ColorFitResult:
        nonlocal called
        called = True
        return ColorFitResult(
            status=ColorFitStatus.FITTED,
            input_path=str(source),
            output_path=str(output),
            input_size_bytes=8,
            output_size_bytes=4,
            target_bytes=10_000,
            route=Route.VECTOR_COLOR.value,
            dpi=FIXED_COLOR_DPI,
            jpeg_quality=90,
            page_count=1,
            reasons=("mock reason",),
        )

    monkeypatch.setattr("pdf_size_fit.fit.fit_color_vector_pdf", mock_fit)

    result = fit_pdf(source, output, target_bytes=10_000)

    assert called
    assert result.status is FitStatus.FITTED
    assert result.route is Route.VECTOR_COLOR
'''
if 'test_vector_color_dispatches_to_color_fit' not in content:
    with open('tests/test_fit.py', 'w') as f:
        f.write(content + '\n' + new_test)

    with open('tests/test_fit.py', 'r') as f:
        content = f.read()

    content = content.replace(
        'from pdf_size_fit.image_fit import ImageFitResult, ImageFitStatus',
        'from pdf_size_fit.image_fit import ImageFitResult, ImageFitStatus\nfrom pdf_size_fit.color_fit import ColorFitResult, ColorFitStatus, FIXED_COLOR_DPI'
    )

    with open('tests/test_fit.py', 'w') as f:
        f.write(content)
