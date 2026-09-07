from pypdf import PdfWriter
from pathlib import Path

source = Path("test_color.pdf")
output = Path("test_color_output.pdf")

from tests.test_color_fit import _generate_vector_pdf
from pdf_size_fit.color_fit import fit_color_vector_pdf
import unittest.mock

# Create a mock for diagnosis
with unittest.mock.patch("pdf_size_fit.color_fit.diagnose_pdf") as mock_diagnose:
    from pdf_size_fit.diagnose import Diagnosis, Route
    mock_diagnose.return_value = Diagnosis(
        path="test_color.pdf",
        file_size_bytes=1000000,
        target_bytes=10000,
        page_count=1,
        image_stream_bytes=0,
        vector_stream_bytes=0,
        image_ratio=0.0,
        vector_ratio=1.0,
        rendered_color_fraction=1.0,
        route=Route.VECTOR_COLOR,
        reasons=(),
    )
    _generate_vector_pdf(source, color=True, repeats=8000)
    input_size = source.stat().st_size

    result = fit_color_vector_pdf(source, output, target_bytes=input_size - 100)
    output_size = output.stat().st_size if output.exists() else result.output_size_bytes

    print(f"Input size: {input_size}")
    print(f"Output size: {output_size}")
    print(f"Result: {result}")

if source.exists(): source.unlink()
if output.exists(): output.unlink()
