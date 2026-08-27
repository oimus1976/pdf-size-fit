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

The image route clones the original PDF structure and recompresses unique supported image XObjects through pypdf's public image replacement API.

```powershell
pdf-size-fit-image .\oversize.pdf .\oversize-fit.pdf --target-bytes 10000000
```

By default, downsampling is disabled while that more destructive fallback is still being validated. Explicit opt-in is required:

```powershell
pdf-size-fit-image .\oversize.pdf .\oversize-fit.pdf `
  --target-bytes 10000000 `
  --min-quality 70 `
  --min-scale 0.80
```

The PoC currently:

- starts at full image resolution and JPEG quality 100,
- exhausts the configured full-resolution JPEG-quality range before considering downsampling,
- keeps downsampling disabled by default with `min_scale=1.0`,
- when explicitly enabled, scans 99%, 98%, 97% ... down to the configured scale floor at the minimum JPEG quality and selects the first fitting integer-percent scale,
- then raises JPEG quality at that scale as far as the current quality search permits,
- uses ceiling pixel rounding so integer pixel dimensions do not cross the requested relative scale floor,
- rebuilds every trial from the original PDF rather than repeatedly recompressing a lossy intermediate,
- records both image scale and JPEG quality for each attempt,
- preserves supported image dictionary semantics such as a compatible `/SMask` at full resolution,
- refuses to downsample `/SMask` images until the mask can be resized in lockstep,
- handles shared images nested inside reusable Form XObjects in the current synthetic coverage,
- verifies page count, page boxes, and rotation before accepting output,
- refuses unsupported or unknown image structures rather than silently flattening them,
- refuses signed/certified PDFs,
- refuses PDFs with standard PDF/A identification metadata until conformance after rewriting can be validated,
- returns `target-not-met` without writing output if the configured JPEG-quality and image-scale floors are exhausted,
- never overwrites the input or a pre-existing output file.

`min_scale` is a relative source-pixel floor, not a DPI/readability guarantee. The current resolution-first policy is also provisional: a higher-resolution/lower-JPEG-quality candidate is not guaranteed to look better than a lower-resolution/higher-quality candidate for every document. The current PoC applies one selected scale to all supported images, so automatic/default downsampling will not be considered until representative visual validation and more content-aware policy work are done.

Synthetic preservation tests currently cover a bookmark, a basic AcroForm field/value, and an embedded file in addition to the image-specific cases. This is still narrow PoC coverage, not a broad PDF compatibility claim.

The downsampling fallback remains behind an explicit opt-in gate for this PR. Before it is treated as ready for broader use, the revised safety tests must pass locally and in CI, and a representative real/image-like PDF must be forced through the downsampling path for fixed-condition before/after visual comparison.

## Project stage

This repository currently records experiments and design decisions. Backend libraries, license, packaging method, GUI, and release policy are **not yet finalized**.

Real municipal documents used during local testing must not be committed. Repository fixtures should be synthetic or otherwise safe to redistribute.

See:

- `PROJECT_STATUS.md`
- `CHANGELOG.md`
- `docs/DESIGN.md`
- `docs/TEST_MATRIX.md`
- `docs/LICENSE_REVIEW.md`
