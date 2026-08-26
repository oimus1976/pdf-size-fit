# Project Status

Last updated: 2026-08-26

## Current phase

**Experimental / PoC**

The project is validating whether oversized PDFs can be automatically classified and fitted under a target attachment limit without forcing users to understand PDF internals or compression parameters.

## Validated routes so far

### 1. Image-heavy PDF

A real-world 11-page sample was 10,478,354 bytes and consisted almost entirely of page-sized raster images. Re-encoding the images as JPEG at quality 100, without reducing pixel dimensions, produced 8,767,488 bytes.

Interpretation: some image-heavy PDFs can cross the target threshold with very small visual change and without rasterizing text/vector content that is not responsible for the size.

### 2. Monochrome abnormal vector/outline PDF

A real-world document with almost no embedded raster images had unusually large page content streams dominated by outlined vector text. A PoC using PDFium rendering, 1-bit conversion, and CCITT Group 4 encoding produced a 2,215,863-byte 300 dpi PDF from a 23,375,987-byte test input derived from the original document.

Interpretation: for this class, rasterization can be substantially more effective than normal image-oriented PDF compression.

### 3. Color abnormal vector/outline PDF

A synthetic 12-page fixture containing no embedded images and no extractable text was generated at 17,327,349 bytes. Rasterizing at 200 dpi and encoding as JPEG quality 90 produced 9,475,016 bytes.

Interpretation: a color-vector fallback route is technically plausible, but quality/size search and routing criteria still need work.

## Current design direction

- Process only PDFs that exceed the configured target threshold.
- Diagnose where the file size comes from before modifying the PDF.
- Prefer the least destructive route likely to satisfy the target.
- Stop as soon as the target is met; do not optimize for the smallest possible output.
- Preserve the original input unchanged.
- Keep processing offline with no runtime downloads or required network access.

## Next milestone

Build an **automatic diagnosis and routing PoC** that can distinguish at least:

1. image-heavy PDFs,
2. monochrome abnormal vector/outline PDFs,
3. color abnormal vector/outline PDFs,
4. PDFs already under the target threshold.

The next PoC should report its classification and reasoning before applying any compression.

## Not decided yet

- Final PDF writer library
- Application license
- Packaging / installer method
- GUI framework
- Exact safety margin below a nominal 10 MB limit
- Support policy for signed PDFs, forms, attachments, PDF/A, annotations, or other special features
- Whether image XObjects can always be replaced safely enough for the MVP
