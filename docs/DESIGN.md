# Design Notes

## Problem statement

The primary use case is not general PDF optimization. It is a recovery path for a user who has a PDF that exceeds an attachment-size limit, wants to keep it as one file, and needs the highest practical quality that fits under the target.

## Design goals

- Offline operation.
- Single-PDF input and output for the MVP.
- No runtime downloads or required network access.
- Preserve the original input unchanged.
- Prefer the least destructive transformation that can satisfy the target.
- Stop once the target is met instead of minimizing output size further.
- Keep routing and compression decisions automatic for normal users.
- Record enough processing metadata to make results explainable and reproducible.

## Non-goals for the current PoC

- General PDF editing.
- OCR.
- PDF splitting as a primary feature.
- Producing the smallest possible PDF regardless of quality.
- Treating already-small Word/Excel-derived PDFs as a primary optimization target.
- Supporting every special PDF feature before the core routing hypothesis is validated.

## High-level flow

```text
input PDF
  |
  +-- already below target? --> no compression required
  |
  +-- analyze structure and size contributors
        |
        +-- image-heavy ----------------> image recompression route
        |
        +-- abnormal vector/outline ----> determine monochrome vs color
                                            |
                                            +-- monochrome -> raster + CCITT G4
                                            +-- color ------> raster + JPEG
        |
        +-- unclassified ---------------> do not guess; report unsupported/needs review
```

## Route A: image-heavy PDFs

Working hypothesis:

- Estimate how much of the file is attributable to image XObjects.
- If images dominate, preserve text/vector structures and recompress only images where safe.
- Start with the highest-quality candidate.
- Lower JPEG quality and/or image resolution only as needed to meet the target.

A real-world image-per-page sample crossed the threshold using JPEG quality 100 without reducing pixel dimensions.

## Route B: monochrome abnormal vector/outline PDFs

Working hypothesis:

- Detect PDFs where image streams do not explain the size but page content streams are unusually large.
- Confirm that rendered pages are effectively monochrome.
- Render with PDFium at a high-enough resolution.
- Convert to 1-bit and encode image XObjects with `/CCITTFaxDecode` Group 4 settings.
- Prefer higher DPI when it already satisfies the target.

This route intentionally sacrifices text search/copy and vector scalability, so it should be treated as a fallback for PDFs whose existing representation is pathologically large.

## Route C: color abnormal vector/outline PDFs

Working hypothesis:

- Use the same abnormal-vector detection as Route B.
- Determine that the rendered content materially uses color.
- Rasterize and encode as JPEG.
- Search resolution/quality combinations from higher quality toward lower quality until the target is met.

The current synthetic fixture reached the target at 200 dpi / JPEG quality 90 and also at 180 dpi / quality 92. The search policy is not yet finalized.

## Target-size semantics

A nominal "10 MB" limit is ambiguous unless the receiving system's byte interpretation is known. The production tool should therefore use an explicit byte target internally and likely apply a safety margin rather than aiming exactly at the boundary.

The safety margin is not yet fixed.

## Safety invariants

Before a result is accepted, the PoC should eventually verify at least:

- input file is not overwritten,
- output is a readable PDF,
- page count matches,
- page dimensions/orientation are preserved,
- output size is below the configured byte target,
- processing route and parameters are recorded,
- failed processing does not replace or masquerade as a valid result.

Later testing should cover links, bookmarks, forms, annotations, signatures, embedded files, PDF/A expectations, and other features before claiming broad compatibility.

## Public test data policy

Real municipal documents used during local testing must not be committed. Repository fixtures should be synthetic or have redistribution rights that are clearly documented.

The synthetic fixtures should model the relevant structural pathology rather than reproduce confidential document content.
