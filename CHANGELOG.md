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

### Changed

- Color routing now scans every page at low resolution and uses the maximum per-page color fraction, reducing the risk of incorrectly classifying a partially color document as monochrome.
- Raw-stream sizing falls back to pypdf stream serialization if private `_data` storage is unavailable instead of relying on parsed `/Length`.

### Notes

- No application license has been selected yet.
- No production compression engine, GUI, installer, or release artifact exists yet.
- Real municipal source documents used for local validation are intentionally excluded from the repository.
