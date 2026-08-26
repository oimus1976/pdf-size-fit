# Project Status

Last updated: 2026-08-27

## Current phase

**Experimental / PoC**

The project is validating whether oversized PDFs can be automatically classified and fitted under a target attachment limit without forcing users to understand PDF internals or compression parameters.

## Validated compression routes so far

### 1. Image-heavy PDF

A real-world 11-page sample was 10,478,354 bytes and consisted almost entirely of page-sized raster images. Re-encoding the images as JPEG at quality 100, without reducing pixel dimensions, produced 8,767,488 bytes.

### 2. Monochrome abnormal vector/outline PDF

A real-world document with almost no embedded raster images had unusually large page content streams dominated by outlined vector text. A PoC using PDFium rendering, 1-bit conversion, and CCITT Group 4 encoding produced a 2,215,863-byte 300 dpi PDF from a 23,375,987-byte test input derived from the original document.

### 3. Color abnormal vector/outline PDF

A synthetic 12-page fixture containing no embedded images and no extractable text was generated at 17,327,349 bytes. Rasterizing at 200 dpi and encoding as JPEG quality 90 produced 9,475,016 bytes.

## Automatic diagnosis/routing PoC

The first classifier distinguishes the intended MVP outcomes and reports reasons before any compression is attempted.

Validated against the current representative samples with a 10,000,000-byte target:

- image-heavy real-world sample -> `image-heavy` (encoded images about 99.8% of file size),
- monochrome abnormal-vector real-world sample -> `vector-monochrome` (page/form streams about 99.9%, sampled colored pixels 0.0%),
- color abnormal-vector synthetic fixture -> `vector-color` (page/form streams about 100.0%, sampled colored pixels about 93.9%),
- already-small mixed presentation sample -> `skip`.

The classifier also provides `unclassified` and does not guess a destructive route when no current threshold is met.

A merge-blocking review found that the original color detector sampled only the first pages plus the last page, which could misclassify a PDF whose only color content appeared on an unsampled middle page. The branch now scans every page at low resolution and uses the maximum per-page color fraction, deliberately biasing toward preserving color. A regression test covers the middle-page case.

Current automated coverage includes `skip`, all three routed classes, fail-closed `unclassified`, middle-page color detection, and invalid target rejection. CI is configured for Python 3.11 and 3.12.

## Current design direction

- Process only PDFs that exceed the configured target threshold.
- Diagnose where the file size comes from before modifying the PDF.
- Prefer the least destructive route likely to satisfy the target.
- Stop as soon as the target is met; do not optimize for the smallest possible output.
- Preserve the original input unchanged.
- Keep processing offline with no runtime downloads or required network access.
- Fail closed when routing evidence is insufficient.
- Bias color detection toward false-color rather than false-monochrome results because the latter could destroy information during 1-bit conversion.

## Next milestone

Connect the diagnosis result to **route-specific compression execution and target-size search**, starting with the image-heavy route because it can potentially preserve text/vector structures while changing only the dominant image streams.

Before that route is treated as safe enough for the MVP, verify how image-XObject replacement interacts with shared images, masks, transparency, color spaces, and page/form resource reuse.

## Not decided yet

- Final PDF writer library
- Application license
- Packaging / installer method
- GUI framework
- Exact safety margin below a nominal 10 MB limit
- Support policy for signed PDFs, forms, attachments, PDF/A, annotations, or other special features
- Whether image XObjects can always be replaced safely enough for the MVP
- Final routing thresholds and confidence policy
- Whether the private pypdf raw-stream access should be removed before or during writer-stack selection
