# License Review

Status: **Preliminary / not legal advice**

The application source is licensed under the MIT License in the repository root
`LICENSE`. Third-party components remain governed by their own licenses. This
document records artifact-specific engineering review so application licensing
and bundled dependency obligations are not conflated.

## Issue #13 portable refresh (2026-09-24)

The repository license decision changed after the original Stage 2 artifact:
the application source is now MIT-licensed. The portable build therefore treats
the root `LICENSE` as an artifact-defining input and copies it beside the
executable, `THIRD_PARTY_NOTICES.txt`, and the captured `licenses/` tree.

The pinned Windows runtime and packager closure remains the same as the original
Stage 2 review. However, a refreshed ZIP is not considered reviewed merely
because the dependency versions are unchanged. For each refreshed artifact,
the exact source commit, ZIP bytes/hash, runtime inventory, notice/license
layout, NucBox9 smoke evidence, and work-PC gate must be recorded before Issue
#13 can close.

`THIRD_PARTY_NOTICES.txt` no longer embeds one historical application commit;
the exact source commit is recorded by the build in
`RUNTIME_INVENTORY.txt` and in the source-derived ZIP filename. This avoids a
notice becoming stale when the reviewed application source changes while the
third-party closure does not.

## Issue #13 Stage 2 packaged-artifact review (2026-09-01, historical artifact)

The reviewed artifact is the Windows x64 PyInstaller onedir ZIP described in
`docs/PORTABLE_BUILD.md`, built from application source commit
`1242df81e2a3bc6b0b00ddd9ef19595cb3fb548a`.

Application-license decision for this gate: no open-source application license
is selected. The artifact is restricted to internal evaluation, with all
rights in the application code reserved and public redistribution prohibited
pending an owner/legal decision. This deliberately narrow boundary does not
change or override any third-party license.

Packaged-release checklist status for this exact artifact:

1. **Complete:** runtime and packager dependencies are exact-pinned in
   `packaging/windows/requirements-portable-build.txt`.
2. **Complete:** applicable wheel, CPython, Tcl/Tk, TkDND, OpenSSL, zlib, and
   packager license texts are captured under `licenses/` and copied into the
   ZIP.
3. **Complete for engineering inventory:** the artifact includes a hashed
   `RUNTIME_INVENTORY.txt` covering every bundled EXE, DLL, and PYD. The
   summary in `docs/PORTABLE_BUILD.md` identifies PDFium, CPython, Tcl/Tk,
   TkDND, Pillow native codecs, OpenSSL, zlib, libffi, Visual C++ runtime,
   UCRT/API sets, and the PyInstaller bootloader.
4. **Complete for this gate:** the application is internal-evaluation-only;
   no public application license is inferred.
5. **Complete:** artifact-specific `THIRD_PARTY_NOTICES.txt` is present beside
   the EXE, with full texts in the adjacent `licenses/` directory.
6. **Complete for engineering review:** the final onedir tree was enumerated
   after packaging. Components added by Python/PyInstaller are recorded rather
   than treated as implicit. Legal approval for broader distribution remains
   outside this engineering review.
7. **Complete:** review date, exact versions, source commit, artifact hash,
   license-file provenance, and NucBox9 evidence are recorded in the notice,
   lock file, inventory, and portable-build document.

The pypdfium2 wheel's `dep5-wheel` and
`LicenseRef-PdfiumThirdParty.txt` are preserved for the exact PDFium binary;
Pillow's exact wheel license file is preserved for its compiled codec closure.
PyInstaller is used under its bootloader exception; its `COPYING.txt` is also
included. This remains an engineering record, not a legal compatibility
opinion or approval for public release.

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

**MIT License selected.**

The repository root `LICENSE` contains the application license. Portable
artifacts must include that file. This application license decision does not
replace, override, or summarize third-party license obligations; those remain
tracked separately in `THIRD_PARTY_NOTICES.txt`, `licenses/`, and the
artifact runtime inventory.
