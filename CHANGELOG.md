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

### Notes

- No application license has been selected yet.
- No production backend, GUI, installer, or release artifact exists yet.
- Real municipal source documents used for local validation are intentionally excluded from the repository.
