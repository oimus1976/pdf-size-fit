# Project Status

Last updated: 2026-08-27

## Current phase

**Experimental / PoC**

The project is validating whether oversized PDFs can be automatically classified and fitted under a target attachment limit without forcing users to understand PDF internals or compression parameters.

## Validated compression routes so far

### 1. Image-heavy PDF

A real-world 11-page sample was 10,478,354 bytes and consisted almost entirely of page-sized raster images.

Two PoCs have crossed the nominal 10,000,000-byte threshold without reducing image pixel dimensions:

- an earlier page-reconstruction experiment produced 8,767,488 bytes at JPEG quality 100,
- the structure-preserving image-XObject replacement PoC produced 7,573,276 bytes at JPEG quality 100 while retaining compatible existing soft masks.

The second result is now the preferred engineering direction because it clones the original PDF structure and changes supported image XObjects rather than rebuilding pages.

### 2. Monochrome abnormal vector/outline PDF

A real-world document with almost no embedded raster images had unusually large page content streams dominated by outlined vector text. A PoC using PDFium rendering, 1-bit conversion, and CCITT Group 4 encoding produced a 2,215,863-byte 300 dpi PDF from a 23,375,987-byte test input derived from the original document.

### 3. Color abnormal vector/outline PDF

A synthetic 12-page fixture containing no embedded images and no extractable text was generated at 17,327,349 bytes. Rasterizing at 200 dpi and encoding as JPEG quality 90 produced 9,475,016 bytes.

## Automatic diagnosis/routing PoC

The classifier distinguishes the intended MVP outcomes and reports reasons before any compression is attempted.

Validated against the current representative samples with a 10,000,000-byte target:

- image-heavy real-world sample -> `image-heavy` (encoded images about 99.8% of file size),
- monochrome abnormal-vector real-world sample -> `vector-monochrome` (page/form streams about 99.9%, sampled colored pixels 0.0%),
- color abnormal-vector synthetic fixture -> `vector-color` (page/form streams about 100.0%, sampled colored pixels about 93.9%),
- already-small mixed presentation sample -> `skip`.

The classifier also provides `unclassified` and does not guess a destructive route when no current threshold is met.

A merge-blocking review found that the original color detector sampled only the first pages plus the last page, which could misclassify a PDF whose only color content appeared on an unsampled middle page. The implementation now scans every page at low resolution and uses the maximum per-page color fraction, deliberately biasing toward preserving color. A regression test covers the middle-page case.

## Image-heavy compression execution PoC

The first route-specific execution PoC now:

- requires an `image-heavy` diagnosis before it runs,
- rejects PDFs containing signature fields or certification-permissions structures because rewriting may invalidate signatures,
- clones the original PDF with pypdf,
- replaces each unique supported image XObject through pypdf's public `ImageFile.replace()` API,
- explicitly restores supported image dictionary semantics that `ImageFile.replace()` would otherwise discard, including `/SMask`, `/Interpolate`, `/Intent`, `/StructParent`, `/Metadata`, and `/OC`,
- fails closed on explicitly unsupported or unknown image dictionary semantics,
- starts at JPEG quality 100 and searches downward only when necessary,
- rebuilds every trial from the original input so lossy recompression does not accumulate,
- verifies page count, page boxes, rotation, and final byte size before accepting output,
- refuses to overwrite either the source or a pre-existing destination,
- fails closed on unsupported image structures.

After adversarial review, synthetic automated coverage is `14 passed` in the local review environment, including signed-PDF rejection and preservation of supported image dictionary semantics. The real-world image-heavy sample was also run through this implementation: 10,478,354 -> 7,573,276 bytes at JPEG quality 100. A PDFium full-document render comparison at scale 1 showed page-wise MAE <= about 0.098, maximum channel difference 4, and PSNR >= about 56.9 dB for that sample. These measurements describe that sample only, not a general visual-quality guarantee.

## Current design direction

- Process only PDFs that exceed the configured target threshold.
- Diagnose where the file size comes from before modifying the PDF.
- Prefer the least destructive route likely to satisfy the target.
- Stop as soon as the target is met; do not optimize for the smallest possible output.
- Preserve the original input unchanged.
- Keep processing offline with no runtime downloads or required network access.
- Fail closed when routing evidence is insufficient.
- Bias color detection toward false-color rather than false-monochrome results because the latter could destroy information during 1-bit conversion.
- For image-heavy PDFs, preserve the original PDF structure and replace supported image XObjects rather than reconstructing pages.
- Treat pypdf image replacement as a dictionary replacement operation: explicitly preserve known semantics and reject unknown/unsafe semantics.
- Refuse to rewrite signed/certified PDFs in the current PoC.

## Next milestone

Continue reviewing the image-XObject execution PoC against additional structures before treating the route as MVP-ready. Priority cases include:

1. shared image XObjects reused across pages/forms,
2. images nested inside Form XObjects,
3. additional valid color spaces and bit depths,
4. masks/transparency combinations,
5. bookmarks, forms, embedded files, optional content, and PDF/A expectations,
6. target-not-met behavior when JPEG quality alone is insufficient.

Only after that review should the PoC consider adding image downsampling as a second-stage size search.

## Not decided yet

- Final PDF writer library
- Application license
- Packaging / installer method
- GUI framework
- Exact safety margin below a nominal 10 MB limit
- Support policy for forms, attachments, PDF/A, annotations, or other special features
- Final routing thresholds and confidence policy
- Whether the private pypdf raw-stream access should be removed before or during writer-stack selection
- Whether and how the image route should support downsampling after JPEG-quality search is exhausted
