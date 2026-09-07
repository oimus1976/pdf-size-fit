import re

with open('src/pdf_size_fit/color_fit.py', 'r') as f:
    content = f.read()

# I apparently overwrote the _single_jpeg_image by mistake again when replacing the _result function.
# Wait, actually earlier I generated `_single_jpeg_image` using a script, and maybe I wiped it out?
# Let's add it right before `_build_candidate`.
jpeg_func = '''
def _single_jpeg_image(image: Image.Image, writer: PdfWriter, jpeg_quality: int) -> IndirectObject:
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
    return writer._add_object(stream)

'''

content = re.sub(
    r'(def _build_candidate)',
    jpeg_func + r'\1',
    content,
    count=1
)

with open('src/pdf_size_fit/color_fit.py', 'w') as f:
    f.write(content)
