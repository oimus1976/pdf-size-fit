# Test Matrix

This matrix records experimental evidence, not release guarantees.

Real municipal documents are used only for local/private validation and must not be committed to this repository.

| ID | Sample type | Source | Input | Experimental route | Output | Status / observation |
|---|---|---|---:|---|---:|---|
| T01 | Monochrome abnormal vector/outline | Private real-world sample | 23,375,987 bytes test input derived from the original large PDF | PDFium render -> 1-bit -> CCITT Group 4, 300 dpi | 2,215,863 bytes | Under target; 47 pages re-rendered successfully in PoC verification |
| T02a | Image-heavy, approximately one full-page image per page | Private real-world sample | 10,478,354 bytes | Earlier page-reconstruction experiment, JPEG quality 100 | 8,767,488 bytes | Under target; useful early proof but not preferred structure-preserving design |
| T02b | Same image-heavy sample | Private real-world sample | 10,478,354 bytes | Clone PDF and replace supported image XObjects, JPEG quality 100, preserve compatible `/SMask` | 7,573,276 bytes | Under target; preferred image-route PoC direction |
| T03 | Color abnormal vector/outline | Synthetic fixture | 17,327,349 bytes | PDFium render -> RGB JPEG, 200 dpi / quality 90 | 9,475,016 bytes | Under nominal 10,000,000-byte target |
| T03b | Color abnormal vector/outline | Same synthetic fixture | 17,327,349 bytes | PDFium render -> RGB JPEG, 180 dpi / quality 92 | 9,159,915 bytes | Also under target; not yet selected as preferred search result |
| T04 | Mixed image/text presentation PDF | Private real-world sample | 5,042,912 bytes | No processing | unchanged | Below target; automatic diagnosis returns `skip` |
| T05 | Typical Word/Excel-derived text/table PDFs | Public reference samples used locally | already well below target | No processing | unchanged | Not a primary compression target; useful as skip/regression cases |

## Automatic routing validation

The diagnosis PoC was run against the available representative samples with `target_bytes=10_000_000`:

| Sample | Expected | Observed | Evidence |
|---|---|---|---|
| T01 monochrome abnormal vector | `vector-monochrome` | `vector-monochrome` | images 0.0%; page/form streams 99.9%; sampled colored pixels 0.0% |
| T02 image-heavy | `image-heavy` | `image-heavy` | encoded images 99.8%; page content approximately 0.0% |
| T03 color abnormal vector | `vector-color` | `vector-color` | images 0.0%; page/form streams about 100.0%; sampled colored pixels 93.9% |
| T04 already-small presentation | `skip` | `skip` | 5,042,912 bytes <= 10,000,000-byte target |

Synthetic unit tests exercise all diagnosis outcomes without committing multi-megabyte real-world files.

## Image-route execution validation

The image-XObject execution PoC has synthetic coverage for:

- successful target fitting,
- highest-quality refinement after a coarse quality probe crosses the target,
- source-file immutability,
- compatible `/SMask` preservation,
- annotation and metadata retention,
- no output when the file is already below target,
- no output when diagnosis selects a different route,
- signed/certified PDF refusal,
- preservation of supported image dictionary semantics such as `/Interpolate` and `/StructParent`,
- a shared image XObject nested in a Form XObject and reused across two pages,
- bookmark preservation,
- AcroForm field/value preservation,
- embedded-file preservation,
- fail-closed refusal when standard PDF/A identification metadata is present.

Current local review-suite result after adding this coverage: **`17 passed`**.

The shared-Form fixture confirmed that one nested image reused across two pages remains one shared indirect image after compression and is counted as one replacement. A render comparison also confirmed that both pages remain renderable after replacement; as expected for lossy JPEG recompression, pixel differences exist and this synthetic noise fixture is not used as a perceptual-quality benchmark.

For T02b, the real-world image-heavy sample was rendered with PDFium before and after the structure-preserving quality-100 replacement. Across all 11 pages at render scale 1, the observed page-wise maximum MAE was about 0.098, maximum channel difference was 4, and minimum PSNR was about 56.9 dB. These numbers are sample-specific evidence only.

## T01 notes

The original real-world source was roughly 35.9 MB. The measured CCITT PoC above was run against a 23,375,987-byte PDF24-derived version of the same document so the table does not imply that exact byte-for-byte source-to-output ratio.

The document contained almost no embedded raster images; the size was dominated by page content representing text as vector outlines. Normal image-oriented PDF compression did not address the dominant contributor.

## T02 notes

The 11-page input consisted almost entirely of raster image data. The image stream total accounted for more than 99% of the PDF size in the PoC diagnosis. This is the key counterexample to T01: the least destructive useful operation is image recompression, not whole-page rasterization.

The current preferred PoC keeps the PDF page/object structure and replaces supported image XObjects only. It deliberately fails closed for unsupported image structures rather than flattening them silently.

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

- additional color spaces and bit depths,
- color-key masks and additional transparency combinations,
- optional-content and unusual image dictionary combinations,
- rotated/mixed-size pages,
- very long PDFs and memory limits,
- target-not-met behavior when JPEG quality alone cannot reach the target,
- failure/rollback behavior,
- whether PDF/A support is feasible with a local conformance-validation step rather than unconditional refusal.

Shared Form-XObject images, bookmarks, a basic AcroForm field, embedded files, signed-PDF refusal, and PDF/A-marker refusal now have synthetic regression coverage but are not broad compatibility guarantees.
