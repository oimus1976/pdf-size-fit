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
3. Reject PDFs carrying standard PDF/A XMP identification metadata until the project can verify PDF/A conformance after rewriting.
4. Clone the original PDF instead of rebuilding pages.
5. Visit unique image XObjects, including images nested inside Form XObjects, and replace only supported images using pypdf's public `ImageFile.replace()` API.
6. Deduplicate by indirect object reference so a shared image reused across pages/forms is recompressed once and remains shared.
7. Because `ImageFile.replace()` replaces the image stream dictionary, explicitly preserve supported non-pixel semantics such as `/SMask`, `/Interpolate`, `/Intent`, `/StructParent`, `/Metadata`, and `/OC`.
8. Before building trials, preflight each source-side `/SMask`. Only a dimension-matching mask whose samples prove it is fully opaque is eligible for removal during downsampling; all other soft masks remain a downsampling refusal.
9. When a downsampling trial is built from `PdfWriter(clone_from=...)`, revalidate the writer-side `/SMask` itself before removal. Reader and writer indirect object IDs can be renumbered during cloning, so eligibility must not be transferred by assuming object-ID identity. If writer-side revalidation fails, fail closed.
10. Fail closed if an image has rendering semantics that are explicitly unsupported (`/Decode`, `/Mask`, `/ImageMask`, `/SMaskInData`) or an unknown dictionary key that the PoC cannot prove safe to discard.
11. Start at full image resolution with JPEG quality 100.
12. Search JPEG quality downward to the configured minimum and refine the first fitting interval one quality point at a time.
13. Keep downsampling disabled by default (`min_scale=1.0`). A caller must explicitly select a lower minimum scale to opt in.
14. If opt-in downsampling is enabled and no full-resolution candidate fits, scan integer-percent scales from 99% downward to the configured minimum scale at the configured minimum JPEG quality. The first fitting scale is the largest scale observed by that exhaustive percent-granularity scan; this avoids relying on strict file-size monotonicity across resampled JPEGs.
15. At that selected scale, search JPEG quality again from high to low and select the highest fitting quality found by the current quality search.
16. Rebuild every candidate from the original input, never from a previous lossy candidate.
17. Use ceiling rounding for downsampled pixel dimensions so integer rounding does not cross the requested relative scale floor.
18. Verify page count, media boxes, rotation, and final byte target before copying a candidate to the requested output.

19. Do not overwrite the source or an existing destination.

The fallback therefore uses a lexicographic quality policy: **preserve image resolution first, then maximize JPEG quality within that resolution**, subject to the configured minimum JPEG quality and minimum image scale. This is a provisional PoC policy, not a claim that it maximizes perceptual quality. A lower-resolution/high-JPEG-quality candidate can look better than a higher-resolution/low-JPEG-quality candidate for some photographic content, while text-heavy slide imagery may behave differently.

`min_scale` is only a **relative source-pixel floor**. It is not an effective-DPI, readability, barcode/QR-code, or OCR safety guarantee. For example, reducing a 600 dpi source to 50% is very different from reducing a 120 dpi source to 50%. A future production-quality policy may need page-placement-aware effective-DPI limits instead of, or in addition to, a simple relative scale.

The current fallback applies the selected scale uniformly to all supported image XObjects that it replaces. This is intentionally simple for the PoC but can unnecessarily shrink small logos, codes, or other low-contribution images when one dominant photograph explains most of the file size. Future optimization should consider size contribution and image-specific safety constraints before enabling automatic downsampling by default.

The current conservative supported image set is intentionally narrow: 8-bit `/DeviceRGB` and `/DeviceGray` image XObjects, optionally with a dimension-matching soft mask. Full-resolution JPEG recompression can preserve a compatible `/SMask`. For downsampling, the route may remove only a redundant soft mask that both source-side preflight and writer-side revalidation strictly prove is fully opaque. General `/SMask` images, including masks with any transparency, are still refused because resizing the base image without resizing the mask in lockstep would create mismatched dimensions. The route also fails closed on unsupported color spaces/bit depths, masks/decoding semantics, unknown image dictionary semantics, signed/certified PDFs, or PDF/A-identified PDFs.

Synthetic structure coverage confirms that the current clone-and-replace approach can preserve a shared image nested in a reusable Form XObject, bookmarks, an AcroForm text field/value, and an embedded file in the tested fixtures. These are regression checks, not broad guarantees for every variant of those features.

The PDF/A check is intentionally conservative and limited: it looks for standard PDF/A identification markers in the document metadata. A positive marker blocks rewriting. Absence of a marker is not a general proof that a PDF is not archival/conformance-sensitive.

If the target cannot be met at or above both configured floors, the route returns `target-not-met` and writes no output. The tool should surface another route or a user-visible fallback rather than silently crossing the quality floor.

A real-world image-heavy sample reached the 10,000,000-byte target at full resolution and quality 100; the structure-preserving implementation produced 7,573,276 bytes from a 10,478,354-byte input. The same 11-page sample was also forced through downsampling with a 1,000,000-byte target and fitted at 83% scale / JPEG quality 70, producing 985,422 bytes and replacing 11 images after removing 11 redundant fully opaque `/SMask` references. The adjacent tested candidates, 84% / quality 70 at 1,001,273 bytes and 83% / quality 71 at 1,000,986 bytes, exceeded the target and support the current boundary selection.

Fixed-condition PDFium rendering via pypdfium2 4.30.0 completed for all 11 source/output pages at scale 1, rotation 0, crop 0, RGB, and 1376x768. The sample-specific aggregate results were global MAE 3.104882141500396 and global PSNR 29.99111734310301 dB; the worst page MAE was 3.699295714228036, the minimum page PSNR was 28.72845447939584 dB, and the maximum channel difference was 135. Visual review observed increased mosquito noise around edges while small text remained readable, and judged the output acceptable for this sample's approval-attachment use. This evidence is not a general quality guarantee and does not enable automatic/default downsampling.

## Route B: monochrome abnormal vector/outline PDFs

Current PoC execution boundary:

1. Return `skip` without writing output when the source is already at or below the target.
2. Before any diagnosis or execution rendering, reject encryption, signature/certification structures, any AcroForm presence, embedded or associated files, annotations, PDF/A identification, outlines/bookmarks and unsupported document-level navigation semantics.
3. Reject page geometry that cannot be reproduced safely, including invalid dimensions/rotation, a CropBox different from the MediaBox, additional page boxes, and a non-default UserUnit.
4. Apply strict dictionary allowlists after the specific refusals: the catalog may contain only `/Type` and `/Pages`; page dictionaries may contain only `/Type`, `/Parent`, `/Resources`, `/MediaBox`, `/CropBox`, `/Contents`, `/Rotate`, `/UserUnit`, and `/Annots`, subject to the earlier value checks. Reject all other known or unknown keys rather than silently dropping semantics the rebuilt PDF does not preserve.
5. Require the existing diagnosis to return `vector-monochrome` for the same byte target. A different route returns `route-mismatch` before monochrome-specific text or bilevel inspection. Execution does not make an independent monochrome guess.
6. Inspect text independently with pypdf and PDFium. Refuse by default if either parser detects non-whitespace text. The explicit opt-in requires each parser independently to stay within 8 non-whitespace characters and one non-empty line per page and 256 non-whitespace characters per document, using identical `isspace()` / `splitlines()` / `strip()` normalization. Require exact equality of every page's `(characters, lines)` tuple. Parser exceptions, unavailable text pages, non-string results, and disagreement fail closed. The numeric bounds are provisional PoC guardrails, not a general policy or quality guarantee.
7. Render every page with PDFium at fixed 300 dpi, with annotations disabled and the same rotation compensation used for execution. Require the rendered pixel dimensions to match the dimensions computed from the MediaBox, while permitting at most one pixel of PDFium raster-rounding difference per axis; a difference of two or more pixels on either axis fails closed. This is a raster-size tolerance in pixels, not a page-geometry tolerance in PDF points. Treat luminance 0..32 as near-black, 33..246 as midtone, and 247..255 as near-white. Use Pillow 5x5 minimum/maximum filters to determine whether each midtone has both near-black and near-white support, then apply a 3x3 minimum filter to the unsupported-midtone mask. Refuse if any unsupported pixel survives or if rendering/filter inspection cannot be completed reliably. No percentage threshold remains. Sub-3-pixel grayscale detail at 300 dpi lies below the persistence criterion and may be binarized.
8. Render every page with PDFium at exactly 300 dpi, compensating for the source page rotation while creating the image so the reconstructed page can retain the original `/Rotate` value.
9. Convert each render to 1-bit monochrome and require a `/CCITTFaxDecode` image with Group 4 `/K -1` parameters.
10. Rebuild each page as one image while retaining its exact MediaBox dimensions and rotation.
11. Reopen and verify page count, MediaBox dimensions, rotation, image encoding and final byte size before accepting the candidate.
12. Copy an accepted candidate from temporary storage by exclusively creating the destination; never overwrite the source or an existing output.

There is deliberately no DPI search. If the fixed 300-dpi candidate exceeds the target, the route returns `target-not-met` and writes no output. Lower-DPI behavior requires separate quality validation.

This route intentionally sacrifices vector scalability. It also removes selectable/searchable and search/copy semantics when the bounded text opt-in is used, so accepted results state that loss explicitly. The dual-parser text bounds and persistent bilateral rule remain conservative PoC guardrails rather than general document-policy or image-quality guarantees; later relaxation requires separately reviewed evidence.

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
- input file is not automatically deleted,
- output is a readable PDF,
- page count matches,
- page dimensions/orientation are preserved,
- output size is below the configured byte target,
- processing route and parameters are recorded,
- failed processing does not replace or masquerade as a valid result.

The image-route PoC currently enforces non-overwrite behavior and automates the structural/size checks for accepted outputs, records scale/quality attempt metrics, rejects signed/certified and PDF/A-identified PDFs, and fails closed when image semantics fall outside its current preservation policy.

Compression output is an irreversible derivative. A future GUI should not offer automatic deletion of the original after success or a workflow that replaces the original with the compressed output. The tool should state that the original may need to be retained. It also should not unconditionally create a backup in another location: unsolicited copies can increase the exposure of personal information or official records. The responsible organization, rather than the tool, should determine the original's storage location and retention period.

Whether an electronically submitted compressed copy becomes an organizationally retained record, and how originals, authoritative copies, and retention duties are handled, depends on the adopting organization's document-management rules and electronic-approval operations. Production adoption must review those rules; the design must not generalize that an electronic-approval attachment is always the legal or institutional original.

Remaining high-priority coverage includes additional color spaces/bit depths, color-key masks and transparency variants, optional-content combinations, rotated/mixed-size pages, very long files, and memory behavior.

## Public test data policy

Real municipal documents used during local testing must not be committed. Repository fixtures should be synthetic or have redistribution rights that are clearly documented.

The synthetic fixtures should model the relevant structural pathology rather than reproduce confidential document content.
