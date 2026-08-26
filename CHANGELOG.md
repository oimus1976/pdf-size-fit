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

### Changed

- Color routing now scans every page at low resolution and uses the maximum per-page color fraction, reducing the risk of incorrectly classifying a partially color document as monochrome.
- Raw-stream sizing falls back to pypdf stream serialization if private `_data` storage is unavailable instead of relying on parsed `/Length`.
- The image-heavy route now preserves the original PDF object/page structure and replaces only supported image XObjects instead of reconstructing each page in a new PDF.
- Image replacement now preserves a defined set of rendering/structure dictionary entries and fails closed when unknown or explicitly unsupported image dictionary semantics would otherwise be discarded.
- PDFs containing signature fields or certification-permissions structures are rejected by the image execution PoC because a full rewrite may invalidate signatures.
- Standard PDF/A XMP identification markers are now treated as a fail-closed boundary until post-rewrite PDF/A conformance can be validated.
- Restored the repository-level `*.pdf` ignore guard so real/private PDFs are not accidentally staged; only explicitly whitelisted synthetic fixtures under `tests/fixtures/` may be tracked.

### Notes

- No application license has been selected yet.
- No production compression engine, GUI, installer, or release artifact exists yet.
- Real municipal source documents used for local validation are intentionally excluded from the repository.
- Image replacement remains deliberately conservative: unsupported masks, color spaces, bit depths, decoding structures, unknown image dictionary semantics, signed/certified PDFs, or PDF/A-identified PDFs return a fail-closed result rather than being rewritten silently.
