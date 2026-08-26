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
- Fail closed instead of guessing a destructive route when evidence is weak.

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

## Diagnosis PoC

The current classifier uses encoded PDF stream sizes as a first structural signal:

- `image-heavy` when encoded image streams account for at least 60% of the PDF file size,
- abnormal-vector candidate when page/form content streams account for at least 35% and the image-heavy condition is not met,
- `skip` when the file is already at or below the configured byte target,
- otherwise `unclassified`.

For abnormal-vector candidates, PDFium scans all pages at low resolution. Non-white sampled pixels whose RGB channel spread is at least 18 are counted as colored. The classifier uses the maximum per-page colored fraction rather than a document-wide average so a color-only middle page is not hidden by many monochrome pages. A current experimental threshold of 1% colored non-white pixels separates `vector-color` from `vector-monochrome`.

These values are **PoC heuristics, not product guarantees**. They are intentionally function parameters so future corpus testing can change them without rewriting the routing model.

The encoded-stream measurement currently isolates one pypdf private implementation detail (`StreamObject._data`) behind a helper because pypdf does not expose a stable public API for raw encoded stream length. If that private storage detail is unavailable, the helper falls back to pypdf stream serialization instead of relying on `/Length`, which parsed stream objects may not retain. This remains an explicit technical-debt item to revisit during PDF-reader/writer selection.

## Route A: image-heavy PDFs

Current PoC design:

1. Require the structural classifier to return `image-heavy`.
2. Reject PDFs containing signature fields or certification-permissions structures before rewriting.
3. Clone the original PDF instead of rebuilding pages.
4. Visit unique image XObjects and replace only supported images using pypdf's public `ImageFile.replace()` API.
5. Because `ImageFile.replace()` replaces the image stream dictionary, explicitly preserve supported non-pixel semantics such as `/SMask`, `/Interpolate`, `/Intent`, `/StructParent`, `/Metadata`, and `/OC`.
6. Fail closed if an image has rendering semantics that are explicitly unsupported (`/Decode`, `/Mask`, `/ImageMask`, `/SMaskInData`) or an unknown dictionary key that the PoC cannot prove safe to discard.
7. Start with JPEG quality 100 and no pixel downsampling.
8. If the target is not met, probe quality downward in coarse steps and refine the first successful interval one quality point at a time.
9. Rebuild each candidate from the original input, never from a previous lossy candidate.
10. Verify page count, media boxes, rotation, and final byte target before copying a candidate to the requested output.
11. Do not overwrite the source or an existing destination.

The current conservative supported set is intentionally narrow: 8-bit `/DeviceRGB` and `/DeviceGray` image XObjects, optionally with a dimension-matching soft mask. The route fails closed on unsupported color spaces/bit depths, masks/decoding semantics, unknown image dictionary semantics, or signed/certified PDFs.

The route currently searches JPEG quality only. Resolution reduction is deferred until additional structure/quality validation is complete.

A real-world image-heavy sample reached the 10,000,000-byte target at quality 100 without downsampling. The structure-preserving implementation produced 7,573,276 bytes from a 10,478,354-byte input.

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

The image-route PoC currently automates the first five of these for accepted outputs, records quality/attempt metrics, rejects signed/certified PDFs, and fails closed when image semantics fall outside its current preservation policy.

Later testing should cover bookmarks, forms, embedded files, PDF/A expectations, shared image resources, Form XObject nesting, optional content, unusual color spaces, and other features before claiming broad compatibility.

## Public test data policy

Real municipal documents used during local testing must not be committed. Repository fixtures should be synthetic or have redistribution rights that are clearly documented.

The synthetic fixtures should model the relevant structural pathology rather than reproduce confidential document content.
