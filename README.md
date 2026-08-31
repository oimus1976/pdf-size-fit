# pdf-size-fit

Status: **Experimental / PoC**

`pdf-size-fit` explores an offline way to fit oversized PDF files under attachment-size limits (for example, 10 MB) while preserving as much readable quality as practical and keeping the document as a single PDF.

## Intended use case

1. A user tries to upload a PDF to an electronic approval or document system.
2. The upload fails because the PDF exceeds the attachment-size limit.
3. Splitting the PDF is undesirable.
4. The tool analyzes the PDF and applies the least destructive strategy that can bring it under the target size.

The initial target is **single-file, offline processing**. The project is not intended to be a general-purpose PDF editor or the smallest-possible PDF compressor.

## Current hypotheses

Three compression routes are under investigation:

1. **Image-heavy PDFs** - recompress image XObjects while preserving text/vector content where possible.
2. **Abnormally heavy monochrome vector/outline PDFs** - rasterize and encode as 1-bit CCITT Group 4.
3. **Abnormally heavy color vector/outline PDFs** - rasterize and encode as JPEG, searching for the highest-quality settings that satisfy the target size.

The preferred behavior is to make no change when a PDF is already below the configured threshold.

## Integrated automatic fitting

The integrated backend diagnoses the input and automatically dispatches only to the two currently implemented execution routes:

```powershell
pdf-size-fit .\oversize.pdf .\oversize-fit.pdf --target-bytes 10000000
```

It returns success without writing output for `skip`, delegates `image-heavy` and `vector-monochrome` to their existing fail-closed fitters, and refuses `vector-color` and `unclassified` without writing output. Callers do not choose the PDF-internal route. Machine-readable output is available with `--json`.

The integrated command preserves the existing route controls and defaults. Image downsampling remains off unless `--min-scale` is set below `1.0`; `--min-quality` keeps the image route's existing default of `70`. Small searchable-text rasterization on the monochrome route remains off unless `--allow-small-searchable-text-rasterization` is explicitly supplied, and monochrome rendering remains fixed at 300 dpi.

## Windows GUI quick start

The source checkout includes a minimal Tkinter GUI for interactive use on Windows. Complete the one-time setup from PowerShell in the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Then double-click `start-pdf-size-fit.cmd`. The launcher uses `.venv\Scripts\pythonw.exe` and shows setup instructions instead of silently closing if the expected runtime or installed project is missing. The same GUI is available through the `pdf-size-fit-gui` Python entry point.

Choose an input PDF and a separate output path. The GUI suggests a non-existing `name-fit.pdf` (or numbered variant), uses decimal MB (`1 MB = 1,000,000 bytes`), and runs the existing integrated `fit_pdf` backend without duplicating route selection. Its defaults preserve the backend safety policy: 10 MB target, minimum JPEG quality 70, image scale 100% (downsampling off), and searchable-text rasterization unchecked. It never replaces or deletes the original or overwrites an existing destination.

This GUI is a source-checkout usability MVP, not a packaged or distributable release. It is not an EXE or installer and does not auto-download dependencies at startup.

The route-specific diagnosis and fitting commands below remain available.

## Diagnosis PoC

The automatic routing classifier reports the proposed route and evidence before compression is attempted.

```powershell
python -m pip install -e ".[dev]"
pdf-size-fit-diagnose .\sample.pdf
```

Use an explicit byte target when testing a receiving system:

```powershell
pdf-size-fit-diagnose .\sample.pdf --target-bytes 10000000 --json
```

Current route names are `skip`, `image-heavy`, `vector-monochrome`, `vector-color`, and `unclassified`. The classifier intentionally fails closed to `unclassified` when the current heuristics do not justify a destructive route.

## Image-heavy fitting PoC

The image route clones the original PDF structure and recompresses unique supported image XObjects through pypdf's public image replacement API.

```powershell
pdf-size-fit-image .\oversize.pdf .\oversize-fit.pdf --target-bytes 10000000
```

By default, downsampling is disabled. Fixed-condition validation has been completed for one representative real-world sample, but the destructive fallback remains explicit opt-in:

```powershell
pdf-size-fit-image .\oversize.pdf .\oversize-fit.pdf `
  --target-bytes 10000000 `
  --min-quality 70 `
  --min-scale 0.80
```

The PoC currently:

- starts at full image resolution and JPEG quality 100,
- exhausts the configured full-resolution JPEG-quality range before considering downsampling,
- keeps downsampling disabled by default with `min_scale=1.0`,
- when explicitly enabled, scans 99%, 98%, 97% ... down to the configured scale floor at the minimum JPEG quality and selects the first fitting integer-percent scale,
- then raises JPEG quality at that scale as far as the current quality search permits,
- uses ceiling pixel rounding so integer pixel dimensions do not cross the requested relative scale floor,
- rebuilds every trial from the original PDF rather than repeatedly recompressing a lossy intermediate,
- records both image scale and JPEG quality for each attempt,
- preserves supported image dictionary semantics such as a compatible `/SMask` at full resolution,
- when downsampling, removes a redundant `/SMask` only if it can prove that the mask is fully opaque, using source-side preflight and writer-side revalidation that does not depend on indirect object IDs remaining stable,
- applies a strict soft-mask dictionary allowlist before removing a fully opaque `/SMask`; optional-content, metadata, and unknown semantics fail closed,
- refuses to downsample images with any other `/SMask`, including masks that contain transparency,
- handles shared images nested inside reusable Form XObjects in the current synthetic coverage,
- verifies page count, page boxes, and rotation before accepting output,
- refuses unsupported or unknown image structures rather than silently flattening them,
- refuses signed/certified PDFs,
- refuses PDFs with standard PDF/A identification metadata until conformance after rewriting can be validated,
- returns `target-not-met` without writing output if the configured JPEG-quality and image-scale floors are exhausted,
- never overwrites the input or a pre-existing output file.

`min_scale` is a relative source-pixel floor, not a DPI/readability guarantee. The current resolution-first policy is also provisional: a higher-resolution/lower-JPEG-quality candidate is not guaranteed to look better than a lower-resolution/higher-quality candidate for every document. The current PoC applies one selected scale to all supported images. One 11-page sample was forced through the fallback and fitted below a 1,000,000-byte target at 83% scale / JPEG quality 70; fixed-condition PDFium rendering and visual review found the result acceptable for that sample's approval-attachment use. This is sample- and use-specific evidence, not a general quality guarantee or permission to enable automatic/default downsampling.

Synthetic preservation tests currently cover a bookmark, a basic AcroForm field/value, and an embedded file in addition to the image-specific cases. This is still narrow PoC coverage, not a broad PDF compatibility claim.

The downsampling fallback remains behind an explicit opt-in gate. The current head has 31 passing tests in the dedicated supported local venv, and GitHub Actions run #33 passed on Python 3.11 and 3.12 before the subsequent documentation-only refresh. The representative forced-downsampling result was reproduced exactly after the stricter soft-mask allowlist fix.

Compression is irreversible. The tool does not overwrite or automatically delete the input, and users may need to retain the original according to their organization's document-management rules. A future GUI should not offer a post-success "replace/delete original" shortcut, nor should the tool create an unsolicited backup copy that could unnecessarily duplicate sensitive or official records.

## Monochrome vector fitting PoC

The monochrome vector route is deliberately limited to the validated fixed-condition experiment:

```powershell
pdf-size-fit-monochrome .\oversize.pdf .\oversize-fit.pdf `
  --target-bytes 10000000
```

It runs only when the existing diagnosis selects `vector-monochrome` for the same target. Every page is rendered by PDFium at exactly 300 dpi, converted to 1-bit monochrome, and encoded with CCITT Group 4. There is no DPI search: if that one candidate exceeds the target, the route returns `target-not-met` and writes no output. `--dpi` exists only to make the fixed condition explicit; values other than 300 are rejected.

Whole-page rasterization destroys selectable text, vector scalability, and unsupported interactive/document semantics. The route therefore fails closed before diagnosis rendering when it finds encryption, signatures or certification permissions, any AcroForm, embedded/associated files, annotations, PDF/A identification, outlines/bookmarks or other document-level navigation semantics, non-default user units, or page geometry it cannot reproduce safely. After these specific checks, strict catalog, raw `/Pages`-tree-node, and raw/effective leaf-page allowlists reject every key that the initial PoC does not explicitly reconstruct. The raw tree walk also requires reliable indirect identity, matching parent links and descendant counts, exact `/Pages` or `/Page` types, no repeated nodes/cycles/duplicate leaves, and exact agreement with pypdf's flattened page order. Legitimate inherited MediaBox and Rotate values remain allowed and are then validated as effective page geometry.

An explicit `--allow-small-searchable-text-rasterization` flag relaxes only the text refusal. pypdf and PDFium must each independently report at most 8 non-whitespace characters and one non-empty line per page and at most 256 non-whitespace characters for the document, and their normalized `(characters, lines)` tuple must agree exactly on every page. Either parser detecting text still refuses by default. Parser exceptions, unavailable text pages, non-string results, or metric disagreement fail closed. Successful opt-in output reports that selectable/searchable and search/copy semantics were lost. These numeric limits are provisional PoC guardrails, not a general document policy or quality guarantee.

Before grayscale inspection, the safety gate separately renders every page at the same fixed 300 dpi in RGB with annotations disabled. Any pixel whose RGB channel spread is at least 16 refuses the document; no page-area percentage can hide a small saturated mark. The threshold is a conservative provisional PoC guardrail, not a general color-science guarantee. The gate then performs its separate 8-bit grayscale render: near-black is luminance 0 through 32, midtone is 33 through 246, and near-white is 247 through 255. Pillow 5x5 minimum/maximum filters determine whether each midtone has both near-black and near-white edge support. Unsupported midtones are filtered again with a 3x3 minimum filter; any surviving pixel means a persistent unsupported-midtone region and refuses the document. There is no percentage threshold. Sub-3-pixel grayscale detail at 300 dpi lies below this persistence criterion and may be binarized, so the rule is a provisional PoC guardrail rather than a general quality guarantee. RGB/grayscale rendering or inspection failures fail closed, with the same one-pixel-per-axis raster-rounding allowance. Candidate generation remains PDFium `grayscale=True` followed by Pillow `.convert("1")`. Accepted documents retain page count, MediaBox dimensions, and rotation; the route verifies the 1-bit CCITT G4 output with pypdf and never overwrites the input or an existing destination.

Only synthetic fixtures are included in the regression suite. Private municipal PDFs remain outside the repository and are reserved for the separate real-file validation gate.

## Project stage

This repository currently records experiments and design decisions. Backend libraries, license, packaging method, and release policy are **not yet finalized**. The Windows GUI is only a source-checkout usability MVP, not a packaged release.

Real municipal documents used during local testing must not be committed. Repository fixtures should be synthetic or otherwise safe to redistribute.

See:

- `PROJECT_STATUS.md`
- `CHANGELOG.md`
- `docs/DESIGN.md`
- `docs/TEST_MATRIX.md`
- `docs/LICENSE_REVIEW.md`
