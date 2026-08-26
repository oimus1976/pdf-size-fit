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

The second result is the preferred engineering direction because it clones the original PDF structure and changes supported image XObjects rather than rebuilding pages.

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

## Image-heavy compression execution PoC

The route-specific execution PoC now:

- requires an `image-heavy` diagnosis before it runs,
- rejects PDFs containing signature fields or certification-permissions structures because rewriting may invalidate signatures,
- rejects PDFs carrying standard PDF/A identification metadata until post-rewrite conformance can be validated,
- clones the original PDF with pypdf,
- replaces each unique supported image XObject through pypdf's public `ImageFile.replace()` API,
- explicitly restores supported image dictionary semantics that `ImageFile.replace()` would otherwise discard,
- fails closed on explicitly unsupported or unknown image dictionary semantics,
- starts at JPEG quality 100 and searches downward only when necessary,
- rebuilds every trial from the original input so lossy recompression does not accumulate,
- verifies page count, page boxes, rotation, and final byte size before accepting output,
- refuses to overwrite either the source or a pre-existing destination.

The adversarial review suite has expanded from 14 to **17 passing tests** in the local review environment.

Newly validated structure cases:

- a shared image XObject nested inside one Form XObject and reused across two pages remains a single shared indirect image after fitting; the image is replaced once,
- a synthetic bookmark is preserved,
- an AcroForm text field and its value are preserved,
- an embedded file and its bytes are preserved,
- a PDF carrying standard PDF/A XMP identification metadata is rejected with `pdf-a-unsupported` and no output file.

The real-world image-heavy sample remains 10,478,354 -> 7,573,276 bytes at JPEG quality 100. A PDFium full-document render comparison at scale 1 showed page-wise MAE <= about 0.098, maximum channel difference 4, and PSNR >= about 56.9 dB for that sample. These measurements describe that sample only, not a general visual-quality guarantee.

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
- Refuse to rewrite signed/certified PDFs and PDF/A-identified PDFs in the current PoC.

## Next milestone

Continue narrowing the remaining image-route compatibility gaps before adding image downsampling. Priority cases are now:

1. additional valid color spaces and bit depths,
2. color-key masks and more transparency combinations,
3. optional-content and unusual image dictionary combinations,
4. rotated/mixed-size pages,
5. long-document and memory behavior,
6. target-not-met behavior when JPEG quality alone is insufficient,
7. a deliberate decision on whether PDF/A support requires an external/local conformance validator.

Shared Form-XObject images, bookmarks, AcroForms, and embedded files now have synthetic preservation coverage; they are no longer completely untested areas, but this does not yet justify broad compatibility claims.

## Not decided yet

- Final PDF writer library
- Application license
- Packaging / installer method
- GUI framework
- Exact safety margin below a nominal 10 MB limit
- Support policy for wider forms/attachments/PDF/A/annotation cases
- Final routing thresholds and confidence policy
- Whether the private pypdf raw-stream access should be removed before or during writer-stack selection
- Whether and how the image route should support downsampling after JPEG-quality search is exhausted
