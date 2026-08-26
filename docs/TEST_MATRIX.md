# Test Matrix

This matrix records experimental evidence, not release guarantees.

Real municipal documents are used only for local/private validation and must not be committed to this repository.

| ID | Sample type | Source | Input | Experimental route | Output | Status / observation |
|---|---|---|---:|---|---:|---|
| T01 | Monochrome abnormal vector/outline | Private real-world sample | 23,375,987 bytes test input derived from the original large PDF | PDFium render -> 1-bit -> CCITT Group 4, 300 dpi | 2,215,863 bytes | Under target; 47 pages re-rendered successfully in PoC verification |
| T02 | Image-heavy, approximately one full-page image per page | Private real-world sample | 10,478,354 bytes | Re-encode page images as JPEG quality 100; keep pixel dimensions | 8,767,488 bytes | Under target with small measured pixel differences in sampled pages |
| T03 | Color abnormal vector/outline | Synthetic fixture | 17,327,349 bytes | PDFium render -> RGB JPEG, 200 dpi / quality 90 | 9,475,016 bytes | Under nominal 10,000,000-byte target |
| T03b | Color abnormal vector/outline | Same synthetic fixture | 17,327,349 bytes | PDFium render -> RGB JPEG, 180 dpi / quality 92 | 9,159,915 bytes | Also under target; not yet selected as preferred search result |
| T04 | Mixed image/text presentation PDF | Private real-world sample | already below target | No processing | unchanged | Expected behavior is skip/no compression |
| T05 | Typical Word/Excel-derived text/table PDFs | Public reference samples used locally | already well below target | No processing | unchanged | Not a primary compression target; useful as skip/regression cases |

## T01 notes

The original real-world source was roughly 35.9 MB. The measured CCITT PoC above was run against a 23,375,987-byte PDF24-derived version of the same document so the table does not imply that exact byte-for-byte source-to-output ratio.

The document contained almost no embedded raster images; the size was dominated by page content representing text as vector outlines. Normal image-oriented PDF compression did not address the dominant contributor.

## T02 notes

The 11-page input consisted almost entirely of raster image data. The image stream total accounted for more than 99% of the PDF size in the PoC diagnosis. This is the key counterexample to T01: the least destructive useful operation is image recompression, not whole-page rasterization.

## T03 notes

The synthetic fixture was intentionally constructed with:

- 12 A4 pages,
- zero embedded images,
- zero extractable text,
- large color vector/path content,
- a file size above the target threshold.

It exists to validate routing and the color-vector fallback without placing real municipal content in source control.

## Acceptance checks to automate later

- output opens successfully,
- page count is unchanged,
- media-box/page dimensions are unchanged,
- output is below the configured byte target,
- input is not modified,
- selected route and parameters are logged,
- representative rendered output remains legible.

## Missing coverage

The current evidence is intentionally narrow. Before broad compatibility claims, add tests for at least:

- PDFs with links/bookmarks,
- annotations/forms,
- signed PDFs,
- embedded files,
- transparency and unusual color spaces,
- rotated/mixed-size pages,
- very long PDFs and memory limits,
- failure/rollback behavior.
