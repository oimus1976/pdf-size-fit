# Changelog

All notable project changes should be recorded in this file.

The project is currently experimental and does not yet use formal releases.

## [Unreleased]

### Added

- Initial repository documentation and project scope.
- Intended use case: fit a single oversized PDF under an attachment-size limit without splitting when practical.
- Three experimental compression-route hypotheses:
  - image-heavy PDFs -> recompress image XObjects,
  - monochrome abnormal vector/outline PDFs -> rasterize to 1-bit CCITT Group 4,
  - color abnormal vector/outline PDFs -> rasterize to JPEG.
- Initial real-world and synthetic PoC measurements in `docs/TEST_MATRIX.md`.
- Initial design constraints and safety assumptions in `docs/DESIGN.md`.
- Preliminary dependency/license review in `docs/LICENSE_REVIEW.md`.
- Automatic diagnosis/routing PoC with explicit `skip`, `image-heavy`, `vector-monochrome`, `vector-color`, and fail-closed `unclassified` results.
- CLI entry point that reports route metrics and reasons without modifying the input PDF.
- Synthetic fixture generator and unit tests for the currently supported routing outcomes.
- Python project metadata and a GitHub Actions test workflow.
- Regression coverage for color content appearing only on a middle page.
- Validation for invalid target-byte values and fail-closed `unclassified` behavior.
- CI coverage for Python 3.11 and 3.12.
- Image-heavy target-size fitting PoC using pypdf's public image replacement API.
- Image-fit CLI with target-byte and minimum-quality controls.
- Quality search that starts at JPEG quality 100, probes downward, and refines the first successful interval without cumulative recompression.
- Tests for image-route fitting, source immutability, compatible soft-mask preservation, annotation/metadata retention, skip behavior, and route-mismatch fail-closed behavior.
- Regression tests that reject PDFs containing signature fields and verify preservation of supported image dictionary semantics such as `/Interpolate` and `/StructParent`.
- Structure-coverage tests for shared image XObjects nested in reusable Form XObjects, bookmark preservation, AcroForm field preservation, and embedded-file preservation.
- PDF/A identification-metadata detection for the image route; matching PDFs return `pdf-a-unsupported` without writing output.
- Second-stage image downsampling fallback for image-heavy PDFs when full-resolution JPEG quality search cannot meet the target.
- `--min-scale` CLI control, per-attempt scale reporting, and selected-scale result metadata.
- Regression coverage for explicit `target-not-met`, downsampling order, minimum-scale exhaustion, and soft-mask fail-closed behavior.
- Additional adversarial-review regression coverage for default downsampling opt-in, pixel-dimension scale floors, and largest-fitting integer-percent scale selection.
- Regression coverage for `PdfWriter(clone_from=...)` renumbering image indirect object IDs, confirming that opaque-soft-mask handling does not depend on reader/writer ID identity.
- Regression coverage ensuring fully opaque soft masks with `/OC` or unknown dictionary keys are not treated as safely removable.
- Recorded 31-test validation in the dedicated supported local venv, plus GitHub Actions success on Python 3.11 and 3.12 for the safety-fix code head.
- Sample-specific real-world forced-downsampling and fixed-condition render-validation evidence; detailed measurements are in `docs/TEST_MATRIX.md`.
- Fail-closed monochrome-vector execution module and CLI using fixed 300 dpi PDFium rendering, 1-bit conversion, and CCITT Group 4 encoding with no DPI search.
- Synthetic monochrome-route regression coverage for successful fitting, immutable inputs, exclusive destinations, route/target outcomes, structural preservation, and destructive-rasterization safety refusals.
- Integrated `fit_pdf` backend API and `pdf-size-fit` CLI that automatically dispatch `image-heavy` and `vector-monochrome` diagnoses to the existing fitters.
- Normalized integrated results with top-level status, diagnosed route, paths, sizes, target, delegated route status, reasons, and nested route-specific details.
- Focused orchestration coverage for dispatch, option forwarding, skip and unsupported no-output behavior, delegated result normalization, CLI JSON/exit codes, and existing-destination protection.
- Dual-parser bounded opt-in for rasterizing a small searchable text layer, with per-page equality and independent pypdf/PDFium boundary coverage.
- Fixed-300-dpi persistent bilateral midtone coverage for hard black/white content, narrow antialias transitions, gray stripes/patches at the provisional boundary, material gray regions, and fail-closed inspection errors.
- Raw page-tree regression coverage for node allowlists, identity/tree invariants, descendant counts, flattened-order agreement, and valid inherited MediaBox/Rotate behavior.
- Fixed-300-dpi RGB chroma-gate coverage for thin and material saturated features, fail-closed inspection, and unchanged grayscale-to-1-bit candidate rendering.
- Minimal Windows-oriented Tkinter GUI that calls the integrated `fit_pdf` backend on a worker thread, preserves existing safe defaults, and reports Japanese status plus detailed backend evidence.
- Collision-free output-name suggestions, exact decimal-MB conversion, input/option validation, and a successful-output folder shortcut without any replace/delete-original action.
- Repository-root `start-pdf-size-fit.cmd` launcher using the local `.venv` Python GUI runtime with readable missing-setup failures, plus the `pdf-size-fit-gui` entry point.
- Headless GUI-helper regression coverage for output safety, target conversion, exact backend argument mapping, status presentation, and launcher/entry-point configuration.
- Default simple GUI centered on `PDFをここにドロップ`, with an in-window D&D target, file picker fallback, and Explorer shell-argument input.
- One fixed simple workflow shared by picker, GUI D&D, and shell input, using an exact `10_000_000`-byte boundary and the existing integrated `fit_pdf` backend for oversized PDFs only.
- Exact no-conversion behavior and Japanese message for PDFs at or below 10,000,000 bytes, plus same-directory `name-fit.pdf`, `name-fit-2.pdf`, ... collision-safe naming for oversized inputs.
- A `詳細設定` disclosure that retains the previous quality, scale, rasterization opt-in, output, and backend-evidence controls while keeping them out of the default simple view.
- Cross-platform GitHub Actions coverage on Ubuntu and Windows for Python 3.11 and 3.12; GUI workflow tests remain headless and display-independent.
- Exact-pinned Windows x64 PyInstaller 6.22.2 onedir packaging, an isolated build script, artifact-level native/runtime inventory, collected license texts, and `THIRD_PARTY_NOTICES.txt`.
- NucBox9 Stage 2 evidence for ZIP-only startup without Python on PATH, Explorer-equivalent shell input, `<=10 MB` no-op, collision-safe oversized synthetic compression, immutability, pypdf/PDFium reopen/render, and zero observed runtime TCP connections.
- Explicit Japanese simple-mode offer to retry only an eligible `image-heavy` `target-not-met` result through the existing bounded downsampling search, with cancellation and no-output failure behavior.
- Headless fallback-flow coverage for offer eligibility, exact option forwarding, cancellation, success evidence, and failure presentation.

### Changed

- Color routing now scans every page at low resolution and uses the maximum per-page color fraction, reducing the risk of incorrectly classifying a partially color document as monochrome.
- Raw-stream sizing falls back to pypdf stream serialization if private `_data` storage is unavailable instead of relying on parsed `/Length`.
- The image-heavy route now preserves the original PDF object/page structure and replaces only supported image XObjects instead of reconstructing each page in a new PDF.
- Image replacement now preserves a defined set of rendering/structure dictionary entries and fails closed when unknown or explicitly unsupported image dictionary semantics would otherwise be discarded.
- PDFs containing signature fields or certification-permissions structures are rejected by the image execution PoC because a full rewrite may invalidate signatures.
- Standard PDF/A XMP identification markers are now treated as a fail-closed boundary until post-rewrite PDF/A conformance can be validated.
- Restored the repository-level `*.pdf` ignore guard so real/private PDFs are not accidentally staged; only explicitly whitelisted synthetic fixtures under `tests/fixtures/` may be tracked.
- Image fitting exhausts the configured full-resolution JPEG-quality range before considering downsampling.
- Downsampling is now opt-in in the PoC: `min_scale` defaults to `1.0`, so existing/default calls retain the pre-downsampling `target-not-met` behavior unless a lower scale is explicitly requested.
- Downsampled pixel dimensions now use ceiling rounding so the requested relative scale floor is not crossed because of integer pixel rounding.
- The fallback now scans integer-percent scales from 99% downward and selects the first fitting scale at the configured minimum JPEG quality instead of assuming file size is monotonic enough for binary search.
- Downsampling may now remove a redundant `/SMask` only when source preflight and writer-side revalidation strictly prove that it is fully opaque; writer revalidation fails closed and does not assume cloned indirect object IDs remain stable.
- Fully opaque soft masks are now accepted as removable only when their image dictionaries contain a strict allowlist of known-safe keys; optional-content, metadata, and unknown semantics fail closed.
- Original-retention requirements now explicitly prohibit automatic input deletion or replacement and avoid unsolicited backup copies; compression is an irreversible derivative whose retention handling belongs to the adopting organization's document-management rules.
- Monochrome execution now requires the existing `vector-monochrome` diagnosis for the same target and rejects unsupported document semantics before diagnosis rendering.
- Integrated fitting treats `skip` as a no-output success and fails closed for `vector-color` and `unclassified`; existing route-specific safety defaults and CLIs remain unchanged.
- Monochrome bilevel preflight now rejects a 3x3-persistent unsupported-midtone region whose centers lack bilateral near-black/near-white support in a 5x5 neighborhood at 300 dpi, instead of using the provisional 72-dpi raw-midtone percentage rule.
- Searchable text remains refused by default; explicit opt-in requires both pypdf and PDFium independently to stay within 8 non-whitespace characters and one non-empty line per page and 256 non-whitespace characters per document and to agree exactly on normalized page metrics, with accepted results recording loss of selectable/searchable and search/copy semantics.
- Monochrome structural preflight now walks the raw `/Pages` tree before flattened pages are trusted, rejecting unknown node/leaf semantics, malformed types/counts/parent links, identity uncertainty, repeated nodes/cycles/duplicate leaves, and raw-to-flattened order disagreement.
- Monochrome destructive safety now rejects any fixed-300-dpi RGB pixel with channel spread at least 16 before the separate grayscale/bilevel inspection; no area-percentage threshold is used, and candidate rendering remains `grayscale=True` then `.convert("1")`.
- Simple mode now refuses to call the fitting backend for inputs at or below 10,000,000 bytes and never silently enables image downsampling or searchable-text rasterization.
- The simple workflow still begins at `min_scale=1.0`; only explicit confirmation after its eligible image-heavy failure relaxes the floor to `0.50`, while preserving target 10,000,000 bytes, minimum JPEG quality 70, searchable-text rasterization off, collision-safe output, and existing fail-closed safeguards.

### Notes

- No application license has been selected yet.
- No production compression engine, installer, or release artifact exists yet; the GUI remains a source-checkout Stage 1 implementation.
- Real municipal source documents used for local validation are intentionally excluded from the repository.
- Image replacement remains deliberately conservative: unsupported masks, color spaces, bit depths, decoding structures, unknown image dictionary semantics, signed/certified PDFs, or PDF/A-identified PDFs return a fail-closed result rather than being rewritten silently.
- Downsampling still refuses general or transparency-bearing `/SMask` images because the base image and mask are not resized in lockstep. Only a redundant soft mask strictly proven fully opaque may be removed for downsampling.
- The NucBox9 system Python is 3.14.1, but the recorded supported local validation used a dedicated venv rather than that system interpreter.
- `min_scale` is a relative source-pixel floor, not an effective-DPI or readability guarantee. The current fallback also applies one selected scale to all supported images in the document.
- The resolution-first scale/quality policy is provisional and does not claim to maximize perceptual quality across different content types.
- Whether a compressed electronic-approval attachment is an authoritative or retained record depends on the adopting organization's rules; the project does not generalize that it is always the original or legally controlling copy.
- The monochrome-vector route is fixed at 300 dpi; a non-fitting candidate returns `target-not-met` with no output instead of searching lower resolutions.
- The dual-parser small-text limits, RGB channel-spread threshold, and persistent bilateral rule are provisional PoC guardrails, not general policy, color-science, or quality guarantees; sub-3-pixel grayscale detail at 300 dpi may be binarized.
