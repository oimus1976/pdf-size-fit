# License Review

Status: **Preliminary / not legal advice**

The project license and final dependency set are not yet selected. This document records the current engineering constraints so license decisions are not made implicitly through implementation choices.

## Project constraints

The intended deployment requires:

- offline operation,
- no recurring license fee,
- suitability for workplace/business use,
- the possibility of redistribution as an internal or public tool,
- no runtime download requirement,
- clear handling of third-party notices in packaged builds.

## Current dependency candidates

### PDFium / pypdfium2

Current PoCs use PDFium through `pypdfium2` for page rendering.

Engineering expectation: PDFium is a permissively licensed Chromium component and `pypdfium2` is distributed under permissive terms, but a release decision must be based on the exact versions and their bundled third-party license notices. Do not reduce the review to the wrapper package license alone.

### Pillow

Used for image conversion/encoding in PoCs. The exact package version and license files must be captured when dependencies are pinned.

### pypdf

Used in the CCITT Group 4 PoC to construct low-level PDF image objects. The package is expected to use a permissive BSD-style license, but the exact pinned version and license text must be verified before release.

The current PoC accessed a private writer method (`_add_object`), which is an API-stability concern independent of licensing.

### pikepdf / qpdf

Considered as an alternative low-level PDF writer. It was not executed in the current constrained PoC environment because it was not installed and external package installation was unavailable.

Before selection, compare:

- exact licenses and notice obligations,
- Windows packaging complexity,
- native-library dependency footprint,
- stability of the low-level object/stream API,
- maintenance/release cadence.

### ReportLab

Used only as an experimental PDF assembly helper in some PoCs. It is not selected as the production writer. In particular, the initial PNG embedding route was much less space-efficient than inserting CCITT Group 4 image streams directly.

## Dependencies intentionally treated with caution

Ghostscript and MuPDF/PyMuPDF were not selected as the preferred core because their common open-source licensing models can impose stronger copyleft obligations, while commercial licensing is also available from their vendor. That does not mean they are unusable; it means their licensing model does not currently match the project's preferred low-friction redistribution constraints.

Any final decision should be verified against current primary license texts and the intended distribution model.

## Release checklist for third-party licensing

Before any public or internal packaged release:

1. Pin exact dependency versions.
2. Capture each dependency's primary `LICENSE`/`COPYING` files.
3. Enumerate bundled transitive/native components, especially PDFium third-party code.
4. Decide the application license separately from dependency licenses.
5. Produce `THIRD_PARTY_NOTICES` appropriate to the actual packaged artifact.
6. Verify that Windows packaging does not silently add components with incompatible terms.
7. Record the review date and source/version for each license conclusion.

## Application license

**Undecided.**

Do not add MIT, BSD, MPL, or another application license merely for repository completeness until the dependency and distribution review is sufficiently stable.
