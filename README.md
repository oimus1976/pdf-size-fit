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

1. **Image-heavy PDFs** - recompress image XObjects while preserving text/vector content where possible.
2. **Abnormally heavy monochrome vector/outline PDFs** - rasterize and encode as 1-bit CCITT Group 4.
3. **Abnormally heavy color vector/outline PDFs** - rasterize and encode as JPEG, searching for the highest-quality settings that satisfy the target size.

The preferred behavior is to make no change when a PDF is already below the configured threshold.

## Diagnosis PoC

The automatic routing classifier reports the proposed route and evidence before compression is attempted.

```powershell
python -m pip install -e ".[dev]"
pdf-size-fit-diagnose .\sample.pdf
```

Use an explicit byte target when testing a receiving system:

```powershell
pdf-size-fit-diagnose .\sample.pdf --target-bytes 10000000 --json
```

Current route names are `skip`, `image-heavy`, `vector-monochrome`, `vector-color`, and `unclassified`. The classifier intentionally fails closed to `unclassified` when the current heuristics do not justify a destructive route.

## Image-heavy fitting PoC

The image route can clone the original PDF structure, recompress unique supported image XObjects through pypdf's public image replacement API, and search from high JPEG quality downward until the byte target is met.

```powershell
pdf-size-fit-image .\oversize.pdf .\oversize-fit.pdf --target-bytes 10000000
```

The PoC currently:

- starts at JPEG quality 100,
- rebuilds every trial from the original PDF rather than repeatedly recompressing a lossy intermediate,
- refines between coarse quality probes to select the highest tested quality that meets the target,
- preserves supported image dictionary semantics such as a compatible `/SMask`,
- handles shared images nested inside reusable Form XObjects in the current synthetic coverage,
- verifies page count, page boxes, and rotation before accepting output,
- refuses unsupported or unknown image structures rather than silently flattening them,
- refuses signed/certified PDFs,
- refuses PDFs with standard PDF/A identification metadata until conformance after rewriting can be validated,
- never overwrites the input or a pre-existing output file.

Synthetic preservation tests currently cover a bookmark, a basic AcroForm field/value, and an embedded file in addition to the image-specific cases. This is still narrow PoC coverage, not a broad PDF compatibility claim.

## Project stage

This repository currently records experiments and design decisions. Backend libraries, license, packaging method, GUI, and release policy are **not yet finalized**.

Real municipal documents used during local testing must not be committed. Repository fixtures should be synthetic or otherwise safe to redistribute.

See:

- `PROJECT_STATUS.md`
- `CHANGELOG.md`
- `docs/DESIGN.md`
- `docs/TEST_MATRIX.md`
- `docs/LICENSE_REVIEW.md`
