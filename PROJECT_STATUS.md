# Project Status

Last updated: 2026-09-24

## Current phase

**Experimental / PoC**

The GitHub repository is public. The application source is licensed under the MIT License; bundled third-party components retain their respective licenses.

The project is validating whether oversized PDFs can be automatically classified and fitted under a target attachment limit without forcing users to understand PDF internals or compression parameters.

## Integrated automatic fitting backend

The backend provides one `fit_pdf` API and one `pdf-size-fit` command that accept an input PDF, a separate output path, and a configurable byte target (default `10_000_000`). The integrated layer uses the existing diagnosis and automatically dispatches supported `image-heavy`, `vector-monochrome`, and `vector-color` inputs without requiring callers to select a PDF-internal route.

For `image-heavy`, the standard integrated path uses a bounded first-fit policy: full-resolution JPEG quality probes `100 -> 90 -> 75 -> 70`, respecting any higher configured quality floor, and stopping after the first validated candidate that meets the target. Explicitly enabled downsampling uses a small bounded scale-probe set. An explicit opt-in high-quality mode (`FitMode.HIGH_QUALITY`, `--mode high-quality`, or GUI checkbox) uses the retained refinement/best-fit search for `image-heavy` PDFs with dynamic candidate progress reporting while enforcing safe parameter floors (`min_quality >= 70`, `min_scale >= 0.50`). Vector routes safely refuse high-quality mode (`unsupported-mode`).

The integrated backend now has a safe page-splitting fallback. Only an ordinary delegated `target-not-met` result is evaluated for splitting; hard refusals remain terminal. A successful strict split preflight promotes the integrated result to `split-available`, but no split mutation occurs until the user explicitly approves it. Split execution reruns the safety preflight and checks that the source has not changed since approval.

The split engine writes page subsets from the original source into temporary storage, measures actual output sizes, and from each current start page chooses the longest contiguous range that fits the target. It does not rely on equal-page-count heuristics or size monotonicity. Every selected staged part and every published final part is reopened and checked for page range geometry and PDFium renderability. Final names use collision-safe groups such as `name-part-1.pdf` or `name-split-2-part-1.pdf`; existing files are never overwritten. Publication failures roll back final files created by that operation, while temporary candidates are removed with their temporary directory.

Split eligibility is intentionally strict: encrypted PDFs, signatures/certification, PDF/A identification, any AcroForm, annotations, outlines/bookmarks, names/destinations/actions/page labels/threads/tag structure/optional-content collections, embedded or associated files, unsupported page geometry, malformed raw page trees, and unknown catalog/page semantics fail closed. The current range-search upper bound is `N * (N + 1) / 2` unique contiguous ranges for an N-page source; this is a correctness-first PoC policy rather than a claim of globally optimal partitioning.

`skip` succeeds without creating output; `unclassified` remains unsupported and fails closed without creating output. Delegated refusals and target failures are normalized as non-success while retaining route-specific evidence. Image downsampling still defaults off at `min_scale=1.0`, monochrome rendering remains fixed at 300 dpi, and small searchable-text rasterization remains explicit opt-in and off by default. The integration does not overwrite inputs or existing destinations, delete originals, or introduce a product-wide target safety margin.

## Windows simple drag-and-drop GUI

The default source-checkout GUI is now a simple view centered on `PDFをここにドロップ`, with a file picker fallback. Dropping a PDF onto the repository launcher in Explorer is also accepted as a shell argument. Picker, in-window D&D, and shell input converge on the same request builder and integrated `fit_pdf` execution path; compression logic is not duplicated.

Simple mode fixes the boundary at exactly `10_000_000` bytes. Files at or below it return the Japanese no-conversion message without calling the fitting backend or creating output. Oversized inputs use a same-directory exclusive destination: `name-fit.pdf`, `name-fit-2.pdf`, and so on. The input and existing files are never overwritten or deleted.

Quality, image scale, route, and backend evidence are absent from the default view. The prior development controls remain behind `詳細設定`. Simple requests automatically use a bounded image scale floor of `min_scale=0.50` with `min_quality=70` in a single backend request, while searchable-text rasterization remains disabled (`allow_small_searchable_text_rasterization=False`). Advanced GUI default scale remains 100% (`min_scale=1.0`), and direct API/CLI defaults remain unchanged unless explicitly configured. Processing remains on a worker thread and successful runs retain `フォルダーを開く`.

When simple mode produces output and image reduction occurred (`selected_scale < 1.0`), the UI reports the selected scale and quality and warns about possible quality loss. Full-resolution success does not claim image reduction. If target exhaustion is split-eligible, the first worker request ends and the Tk/UI thread displays the split confirmation; only `分割する` starts a second worker/backend request. Cancellation makes no split request. Ineligible target exhaustion retains route-neutral no-output wording. All structural and `/SMask` fail-closed checks remain authoritative.

Tkinter and Tk D&D integration are imported only at GUI startup. Headless tests cover the fixed boundary, no-op behavior, collision naming, immutable destinations, backend argument mapping, D&D parsing, shell/drop path convergence, and simple presentation without starting Tk or requiring a display. GitHub Actions runs the full suite on both Ubuntu and Windows for Python 3.11 and 3.12.

The repository-root `start-pdf-size-fit.cmd` still uses the local `.venv\Scripts\pythonw.exe` for source-checkout development. Issue #13 Stage 2 produced a separate Windows x64 PyInstaller 6.22.2 onedir ZIP from source commit `1242df81e2a3bc6b0b00ddd9ef19595cb3fb548a`. NucBox9 smoke passed for GUI startup, shell-path no-op, collision-safe oversized fitting, immutable inputs/destinations, pypdf/PDFium reopen/render, and runtime network independence. Exact evidence and licensing status are in `docs/PORTABLE_BUILD.md` and `docs/LICENSE_REVIEW.md`. The ZIP is internal-evaluation-only and is not an installer, signed binary, public release, or completion of the separate work-PC gate.

Issue #13 final closeout now requires a refreshed portable artifact from current merged source. Because the repository application license is now MIT, the portable build must include the root `LICENSE` and treat it as an artifact-defining input; the bundled third-party notice must not retain an obsolete application commit/license statement. The refreshed ZIP must receive a new exact hash/runtime inventory, NucBox9 smoke, and work-PC no-Python Stage 3 evidence before Issue #13 is closed.

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

## Monochrome vector compression execution PoC

The route-specific execution PoC now reproduces only the validated fixed condition: PDFium rendering at 300 dpi, 1-bit monochrome conversion, and CCITT Group 4 encoding. It requires the existing diagnosis to select `vector-monochrome` for the same target and does not search DPI. A 300-dpi candidate that remains above the target returns `target-not-met` without an output file.

Because this is destructive whole-page rasterization, a structural preflight gate runs before diagnosis rendering. It refuses encryption, signatures/certification permissions, any AcroForm, embedded/associated files, annotations, PDF/A identification, outlines/bookmarks, unsupported document-level navigation semantics, and page geometry outside the currently proven boundary. Minimal catalog, raw `/Pages` node, and leaf-page allowlists reject every dictionary key the route does not reconstruct. The raw page-tree traversal also validates indirect identity, type, parent links, descendant counts, uniqueness/acyclicity, and exact raw-to-flattened leaf order; inherited MediaBox and Rotate remain accepted only when their effective flattened values pass the existing geometry checks.

Text rasterization has a separate explicit opt-in. pypdf and PDFium must each independently remain within 8 non-whitespace characters and one non-empty line per page and 256 non-whitespace characters per document, and their normalized per-page `(characters, lines)` metrics must agree exactly. Parser uncertainty or disagreement fails closed, and accepted output records that selectable/searchable and search/copy semantics were lost. The numeric limits are provisional PoC guardrails, not a general policy or quality guarantee.

At execution resolution the safety gate first renders every page separately in RGB at fixed 300 dpi and refuses if any pixel has channel spread at least 16; there is no area-percentage exemption for a small saturated mark. It then performs the existing separate 300-dpi grayscale inspection. For each luminance-33..246 midtone it uses Pillow 5x5 minimum/maximum filters to require both luminance-0..32 near-black and luminance-247..255 near-white support, then applies a 3x3 minimum filter to the unsupported mask. Any survivor refuses as a persistent region. The RGB threshold and bilateral rule are provisional PoC guardrails rather than general color-science or quality guarantees. RGB/grayscale rendering, dimensions, pixel access, or filtering uncertainty fails closed; both checks retain the one-pixel-per-axis raster-rounding allowance. Candidate output semantics remain PDFium `grayscale=True` followed by Pillow `.convert("1")`. Accepted output is reopened and checked for page count, MediaBox dimensions, rotation, 1-bit CCITT encoding, and target size before an exclusively created destination is retained.

Synthetic fixtures cover the route and its refusal boundary without placing private municipal documents in the repository. The existing private 47-page sample remains a separate real-file validation gate, including representative small-text visual inspection; the earlier 2,215,863-byte result is comparison evidence rather than a byte-for-byte golden artifact.

## Image-heavy compression execution PoC

The route-specific execution PoC now:

- requires an `image-heavy` diagnosis before it runs,
- rejects PDFs containing signature fields or certification-permissions structures because rewriting may invalidate signatures,
- rejects PDFs carrying standard PDF/A identification metadata until post-rewrite conformance can be validated,
- clones the original PDF with pypdf,
- replaces each unique supported image XObject through pypdf's public `ImageFile.replace()` API,
- explicitly restores supported image dictionary semantics that `ImageFile.replace()` would otherwise discard,
- fails closed on explicitly unsupported or unknown image dictionary semantics,
- starts at full image resolution and JPEG quality 100,
- exhausts the configured full-resolution JPEG-quality range before considering downsampling,
- keeps downsampling disabled by default (`min_scale=1.0`) and requires explicit opt-in,
- when explicitly enabled, scans 99%, 98%, 97% ... down to the configured scale floor at the minimum JPEG quality and selects the first fitting scale,
- uses ceiling pixel rounding so integer dimensions do not cross the configured relative scale floor,
- then raises JPEG quality at that scale as far as the current quality search permits,
- rebuilds every trial from the original input so lossy recompression does not accumulate,
- permits removal during downsampling only for a redundant `/SMask` proven fully opaque by source preflight and writer-side revalidation, without assuming reader/writer indirect object IDs remain equal,
- applies a strict soft-mask dictionary allowlist before treating a fully opaque `/SMask` as redundant; `/OC`, `/Metadata`, and unknown keys fail closed,
- continues to refuse general or transparency-bearing `/SMask` images and fails closed if writer-side revalidation fails,
- verifies page count, page boxes, rotation, and final byte size before accepting output,
- refuses to overwrite either the source or a pre-existing destination.

The current head has **31 passing tests** in the dedicated supported local venv, and GitHub Actions run #33 succeeded on Python 3.11 and 3.12. The system Python version on NucBox9 is 3.14.1, but that is not the runtime used for the recorded supported-environment validation. Coverage includes reader/writer indirect object-ID renumbering plus fail-closed regression cases for optional-content and unknown soft-mask dictionary keys.

Previously validated structure cases remain:

- a shared image XObject nested inside one Form XObject and reused across two pages remains a single shared indirect image after fitting; the image is replaced once,
- a synthetic bookmark is preserved,
- an AcroForm text field and its value are preserved,
- an embedded file and its bytes are preserved,
- a PDF carrying standard PDF/A XMP identification metadata is rejected with `pdf-a-unsupported` and no output file.

The real-world image-heavy sample remains 10,478,354 -> 7,573,276 bytes at full resolution and JPEG quality 100 for the ordinary 10,000,000-byte target. For forced-fallback validation, the same 11-page sample used a 1,000,000-byte target, `min_quality=70`, and `min_scale=0.50`; it produced 985,422 bytes at selected scale 0.83 / quality 70, replaced 11 images, and removed 11 redundant fully opaque `/SMask` references. After the stricter soft-mask allowlist fix, the same private sample reproduced the same 985,422-byte / 0.83 / quality-70 result exactly. The tested boundary candidates at 84% / quality 70 (1,001,273 bytes) and 83% / quality 71 (1,000,986 bytes) both exceeded the target.

PDFium rendering through pypdfium2 4.30.0 completed on every source/output page at scale 1, rotation 0, crop 0, RGB, and 1376x768. Sample-specific results were: maximum page MAE 3.699295714228036 (page 7), maximum channel difference 135 (page 8), minimum PSNR 28.72845447939584 dB (page 7), global MAE 3.104882141500396, and global PSNR 29.99111734310301 dB. Visual review observed more edge mosquito noise, while small text remained readable; the output was considered acceptable for this sample's approval-attachment use. This does not establish general quality or justify default downsampling.

## Current design direction

- Process only PDFs that exceed the configured target threshold.
- Diagnose where the file size comes from before modifying the PDF.
- Prefer the least destructive route likely to satisfy the target.
- Stop as soon as the target is met; do not optimize for the smallest possible output.
- Preserve the original input unchanged.
- Do not automatically delete the input, replace it with compressed output, or create an unsolicited backup copy.
- Keep processing offline with no runtime downloads or required network access.
- Fail closed when routing evidence is insufficient.
- Bias color detection toward false-color rather than false-monochrome results because the latter could destroy information during 1-bit conversion.
- For image-heavy PDFs, preserve the original PDF structure and replace supported image XObjects rather than reconstructing pages.
- Treat pypdf image replacement as a dictionary replacement operation: explicitly preserve known semantics and reject unknown/unsafe semantics.
- Refuse to rewrite signed/certified PDFs and PDF/A-identified PDFs in the current PoC.
- Treat minimum JPEG quality and minimum image scale as explicit quality floors. If both are exhausted, return `target-not-met` and write no output.
- Treat relative scale as a PoC control, not an effective-DPI or readability guarantee.
- Treat the current resolution-first scale/quality ordering as a provisional policy rather than a perceptual-quality optimum.

## PR #4 Ready evidence

The branch-readiness evidence is complete for the current head:

1. the current safety-fix head passed 31 tests in the dedicated supported local venv and CI on Python 3.11/3.12,
2. a representative real-world image-heavy PDF was forced through downsampling with an intentionally tighter byte target,
3. all pages were compared at fixed rendering conditions and visually inspected for readability/degradation,
4. the sample-specific evidence is recorded without treating it as a product-wide quality guarantee,
5. the stricter opaque-soft-mask allowlist fix reproduced the same representative output and boundary result.

Remaining compatibility priorities include:

1. additional valid color spaces and bit depths,
2. color-key masks and more transparency combinations,
3. synchronized downsampling for general or transparency-bearing `/SMask` images if it is worth supporting,
4. optional-content and unusual image dictionary combinations,
5. rotated/mixed-size pages,
6. long-document and memory behavior,
7. image-specific/downsampling-by-contribution strategies so low-value size contributors such as small logos or codes are not degraded unnecessarily,
8. a deliberate decision on whether PDF/A support requires an external/local conformance validator,
9. official-record/original-preservation UX and deployment rules, including clear irreversible-output messaging and organization-specific decisions about originals, authoritative records, storage, and retention.

## Not decided yet

- Final PDF writer library
- Packaging / installer method
- GUI framework
- Exact safety margin below a nominal 10 MB limit
- Support policy for wider forms/attachments/PDF/A/annotation cases
- Final routing thresholds and confidence policy
- Whether the private pypdf raw-stream access should be removed before or during writer-stack selection
- Production defaults for minimum JPEG quality and any automatic downsampling policy
- Whether effective DPI or other content-aware limits should replace a simple relative `min_scale` in production
- How each adopting organization's document-management and electronic-approval rules treat originals, compressed attachments, authoritative records, and retention duties
