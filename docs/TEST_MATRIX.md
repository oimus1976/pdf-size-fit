# Test Matrix

This matrix records experimental evidence, not release guarantees.

Real municipal documents are used only for local/private validation and must not be committed to this repository.

| ID | Sample type | Source | Input | Experimental route | Output | Status / observation |
|---|---|---|---:|---|---:|---|
| T01 | Monochrome abnormal vector/outline | Private real-world sample | 23,375,987 bytes test input derived from the original large PDF | PDFium render -> 1-bit -> CCITT Group 4, 300 dpi | 2,215,863 bytes | Under target; 47 pages re-rendered successfully in PoC verification |
| T02a | Image-heavy, approximately one full-page image per page | Private real-world sample | 10,478,354 bytes | Earlier page-reconstruction experiment, JPEG quality 100 | 8,767,488 bytes | Under target; useful early proof but not preferred structure-preserving design |
| T02b | Same image-heavy sample | Private real-world sample | 10,478,354 bytes | Clone PDF and replace supported image XObjects, JPEG quality 100, preserve compatible `/SMask` | 7,573,276 bytes | Under target; preferred image-route PoC direction |
| T02c | Same image-heavy sample, forced downsampling | Private real-world sample | 10,478,354 bytes | 1,000,000-byte target, `min_quality=70`, `min_scale=0.50`; clone and replace at selected scale 0.83 / quality 70 | 985,422 bytes | Fitted; 11 images replaced and 11 redundant fully opaque `/SMask` references removed after source preflight and writer-side revalidation |
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

The merged image-XObject execution PoC has synthetic coverage for:

- successful target fitting,
- highest-quality refinement after a coarse quality probe crosses the target,
- source-file immutability,
- compatible `/SMask` preservation,
- downsampling of images with a redundant fully opaque `/SMask`, with writer-side revalidation independent of reader-side indirect object IDs,
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

The merged review-suite baseline is **`17 passed`**.

The downsampling-fallback branch adds regression cases for:

1. explicit `target-not-met` when downsampling is disabled,
2. downsampling only after full-resolution JPEG-quality exhaustion,
3. source immutability and target-size acceptance for a downsampled result,
4. fail-closed behavior for general or transparency-bearing `/SMask` images, while permitting only strictly proven fully opaque redundant masks to be removed during downsampling,
5. `target-not-met` after exhausting the configured minimum scale,
6. invalid and sub-percent `min_scale` boundary handling,
7. downsampling remaining disabled when the caller accepts the default arguments,
8. ceiling pixel rounding preserving the requested relative scale floor even for very small images,
9. exhaustive descending percent-scale search selecting the largest fitting integer-percent scale at the configured minimum JPEG quality,
10. reader/writer indirect object-ID renumbering via `test_downsampling_allows_opaque_smask_after_writer_renumbers_image_ref`, including writer-side `/SMask` revalidation rather than ID-based matching,
11. fail-closed refusal when a fully opaque soft mask carries `/OC`,
12. fail-closed refusal when a fully opaque soft mask carries an unknown dictionary key.

The current head was validated at **`31 passed`** in the dedicated supported local venv. GitHub Actions run #33 succeeded on Python 3.11 and 3.12 for the safety-fix code head. The NucBox9 system Python is 3.14.1, but the recorded local validation did not use that system interpreter.

The downsampling search is resolution-first and deliberately conservative. After full-resolution quality search fails, downsampling remains off unless the caller explicitly sets `min_scale < 1.0`. When enabled, the current PoC checks 99%, 98%, 97% ... downward at the minimum JPEG quality and chooses the first fitting scale, then searches JPEG quality at that scale. Candidate PDFs are always rebuilt from the original input.

This search policy does **not** claim perceptual optimality. `min_scale` is relative to source pixels rather than effective DPI, and the current PoC applies the same selected scale to every supported image it replaces. Those limitations must be considered before enabling downsampling automatically.

The shared-Form fixture confirmed that one nested image reused across two pages remains one shared indirect image after compression and is counted as one replacement. A render comparison also confirmed that both pages remain renderable after replacement; as expected for lossy JPEG recompression, pixel differences exist and this synthetic noise fixture is not used as a perceptual-quality benchmark.

For T02b, the real-world image-heavy sample was rendered with PDFium before and after the structure-preserving quality-100 replacement. Across all 11 pages at render scale 1, the observed page-wise maximum MAE was about 0.098, maximum channel difference was 4, and minimum PSNR was about 56.9 dB. These numbers are sample-specific evidence only. That sample already fits at full resolution, so it does not validate the new downsampling fallback.

For T02c, the boundary checks were 84% / quality 70 at 1,001,273 bytes (over target), 83% / quality 71 at 1,000,986 bytes (over target), and 83% / quality 70 at 985,422 bytes (fitted). After the stricter soft-mask dictionary allowlist fix, the representative private sample reproduced the same selected result exactly: 985,422 bytes at scale 0.83 / quality 70, 11 images replaced, and 11 redundant fully opaque `/SMask` references removed.

T02c source and output were rendered with PDFium via pypdfium2 4.30.0 using fixed conditions: scale 1, rotation 0, crop `(0,0,0,0)`, RGB, all 11 pages, and 1376x768 for both versions. Every page rendered successfully. Aggregate comparison results were:

- maximum page MAE: 3.699295714228036 (page 7),
- maximum channel difference: 135 (page 8),
- minimum PSNR: 28.72845447939584 dB (page 7),
- global MAE: 3.104882141500396,
- global PSNR: 29.99111734310301 dB.

Visual review found increased mosquito noise around edges, while small text remained readable. The result was considered acceptable for this sample's approval-attachment use. These observations are specific to this sample, render setup, and use; they are not a general quality guarantee.

## T01 notes

The original real-world source was roughly 35.9 MB. The measured CCITT PoC above was run against a 23,375,987-byte PDF24-derived version of the same document so the table does not imply that exact byte-for-byte source-to-output ratio.

The document contained almost no embedded raster images; the size was dominated by page content representing text as vector outlines. Normal image-oriented PDF compression did not address the dominant contributor.

The fixed 300-dpi execution route now has synthetic regression cases for successful 1-bit CCITT Group 4 reconstruction, source immutability, destination non-overwrite, skip and route-mismatch outcomes, explicit `target-not-met`, page-count/MediaBox/rotation preservation, and refusal of signatures/certification structures, any AcroForm, embedded files, annotations, PDF/A identification, encryption, outlines/bookmarks, unsupported crop geometry, invalid rotation, non-whitespace extractable text, and material grayscale/midtone content. Strict catalog/page allowlists are covered with `/Lang`, non-PDF/A `/Metadata`, `/StructParents`, `/Group`, and unknown/custom keys so unreconstructed semantics are rejected instead of silently dropped. Empty or whitespace-only extraction does not itself refuse, the existing minimal black/white vector fixture remains eligible, and a synthetic PDFium inspection failure is covered as fail-closed. The 72-dpi screen treats luminance 33..246 as midtone and refuses a page above 1%; this conservative PoC boundary is not a general quality guarantee. These synthetic cases do not replace the private T01 visual-validation gate, and no private municipal PDF is stored in the repository.

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

## Completed PR #4 readiness validation

The current 31-test suite passed in the dedicated supported local venv, CI passed on Python 3.11/3.12 for the safety-fix code head, a representative real-world image-heavy PDF was forced through the fallback, and fixed-condition rendering plus visual inspection was completed and recorded above. The stricter soft-mask allowlist fix also reproduced the same representative result. These satisfy the recorded Ready conditions for PR #4, not product readiness.

## Missing coverage

The current evidence remains intentionally narrow and should add coverage for at least:

- additional color spaces and bit depths,
- color-key masks and additional transparency combinations,
- synchronized downsampling of general or transparency-bearing `/SMask` images if supported,
- optional-content and unusual image dictionary combinations beyond the current refusal tests,
- rotated/mixed-size pages,
- very long PDFs and memory limits,
- image-specific size-contribution/downsampling decisions,
- failure/rollback behavior,
- whether PDF/A support is feasible with a local conformance-validation step rather than unconditional refusal.

Shared Form-XObject images, bookmarks, a basic AcroForm field, embedded files, signed-PDF refusal, and PDF/A-marker refusal have synthetic regression coverage but are not broad compatibility guarantees.
