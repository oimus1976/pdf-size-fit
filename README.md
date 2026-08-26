# pdf-size-fit

Status: **Experimental / PoC**

`pdf-size-fit` explores an offline way to fit oversized PDF files under attachment-size limits (for example, 10 MB) while preserving as much readable quality as practical and keeping the document as a single PDF.

## Intended use case

1. A user tries to upload a PDF to an electronic approval or document system.
2. The upload fails because the PDF exceeds the attachment-size limit.
3. Splitting the PDF is undesirable.
4. The tool analyzes the PDF and applies the least destructive strategy that can bring it under the target size.

The initial target is **single-file, offline processing**. The project is not intended to be a general-purpose PDF editor or the smallest-possible PDF compressor.

## Current hypotheses

Three compression routes are under investigation:

1. **Image-heavy PDFs** — recompress image XObjects while preserving text/vector content where possible.
2. **Abnormally heavy monochrome vector/outline PDFs** — rasterize and encode as 1-bit CCITT Group 4.
3. **Abnormally heavy color vector/outline PDFs** — rasterize and encode as JPEG, searching for the highest-quality settings that satisfy the target size.

The preferred behavior is to make no change when a PDF is already below the configured threshold.

## Project stage

This repository currently records experiments and design decisions. Backend libraries, license, packaging method, GUI, and release policy are **not yet finalized**.

Real municipal documents used during local testing must not be committed. Repository fixtures should be synthetic or otherwise safe to redistribute.

See:

- `PROJECT_STATUS.md`
- `CHANGELOG.md`
- `docs/DESIGN.md`
- `docs/TEST_MATRIX.md`
- `docs/LICENSE_REVIEW.md`
