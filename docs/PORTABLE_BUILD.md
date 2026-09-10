# Windows Portable Build

Stage 2 was executed on 2026-09-01 on the NucBox9 (Windows 11 Pro,
10.0.26200.9168, x64) against application source commit
`1242df81e2a3bc6b0b00ddd9ef19595cb3fb548a`.

## Reproducible build inputs

Use the supported operator launcher rather than invoking the PowerShell script
directly:

```powershell
.\packaging\windows\build-portable.cmd `
  "C:\path\to\Python312\python.exe" `
  "<exact-source-commit>"
```

The `.cmd` launcher starts Windows PowerShell with `-NoProfile` and
`-ExecutionPolicy Bypass` for that child process only; it does not change the
machine execution policy. Detailed build output is written to
`logs\verification\issue-13-final-portable-build-<timestamp>.log`. On success,
the console shows only the resolved source commit, artifact path, byte count,
SHA-256, and log path. On failure, it shows the durable log path and the final
30 log lines.

Before packaging, the build resolves the requested source reference to an exact
commit and fails closed if the checkout differs from that commit for any
artifact-defining tracked input under `src/`, `pyproject.toml`,
`packaging/windows/`, `THIRD_PARTY_NOTICES.txt`, or `licenses/`. The build also
verifies that the isolated build environment is CPython 3.12.10 x64 before it
records that runtime identity in the artifact inventory.

Runtime packages are pinned to `pypdf==5.9.0`, `pypdfium2==4.30.0`,
`Pillow==12.3.0`, and `tkinterdnd2==0.6.2`. The packager is
`PyInstaller==6.22.2` in `onedir` mode. Its pinned build-only closure is
`altgraph==0.17.5`, `packaging==26.3`, `pefile==2024.8.26`,
`pyinstaller-hooks-contrib==2026.7`, `pywin32-ctypes==0.2.3`, and
`setuptools==84.0.0`. The isolated build uses pip 26.2.1 and CPython 3.12.10
x64; neither the build nor runtime uses the repository `.venv`.

The PowerShell implementation remains available as
`packaging/windows/build-portable.ps1`, but the `.cmd` launcher is the supported
operator entry point on Windows so execution-policy handling and durable logging
are applied consistently. The script is compatible with Windows PowerShell 5.1
and later for the supported build path.

## Stage 2 artifact

`dist/pdf-size-fit-win-x64-source-1242df8.zip` is 23,226,981 bytes with
SHA-256 `46A6406A661146C638E152D98E9956825E2C744183E473F44DB33410B0BD0FC3`.
It contains one top-level `pdf-size-fit/` directory:

- `pdf-size-fit.exe` - 3,736,642 bytes;
- `_internal/` - the CPython and native/application runtime;
- `THIRD_PARTY_NOTICES.txt` and `licenses/` - artifact-specific notices and
  captured license texts;
- `RUNTIME_INVENTORY.txt` - paths, byte sizes, SHA-256 values, and available
  file versions for every bundled EXE, DLL, and PYD.

The extracted tree contains 1,038 files and 48,423,384 bytes. The build is not
code-signed and is an internal-evaluation artifact, not a public release.

## Runtime/native inventory summary

- CPython 3.12.10 x64: `python312.dll`, `base_library.zip`, and standard-library
  PYDs;
- Tcl/Tk 8.6.15: `tcl86t.dll`, `tk86t.dll`, and their Tcl data trees;
- TkDND native payload named 2.10.1 by tkinterdnd2 0.6.2:
  `libtkdnd2.10.1.dll` and the Windows x64 Tcl scripts;
- PDFium 126.0.6462.0: `pypdfium2_raw/pdfium.dll` from pypdfium2 4.30.0;
- Pillow 12.3.0 native modules for core imaging, AVIF, WebP, color management,
  image math, and Tk integration. The captured Pillow license inventory names
  its bundled brotli, FreeType, HarfBuzz, lcms2, libavif, libjpeg-turbo,
  libpng, libwebp, OpenJPEG, TIFF, xz, and zlib-ng components;
- CPython support libraries: OpenSSL 3.0.16 (`libcrypto-3.dll`, `libssl-3.dll`),
  zlib 1.3.1, libffi, Tcl/Tk, the Visual C++ runtime 14.42.34438.0, and Windows
  UCRT/API-set files 10.0.26100.4654;
- PyInstaller 6.22.2 Windows x64 bootloader in `pdf-size-fit.exe`.

See the artifact's `RUNTIME_INVENTORY.txt` for the exhaustive binary list and
hashes and `THIRD_PARTY_NOTICES.txt` for the license index.

## NucBox9 smoke evidence

The final ZIP was expanded into a separate directory and invoked with a PATH
containing only Windows system directories, no repository `.venv`, no system
Python path, and HTTP/HTTPS proxy variables pointing to a refusing local port.

- GUI startup: executable remained running normally after startup.
- Explorer-equivalent shell path input: a PDF path was supplied directly to
  the extracted EXE; this exercises the same code path used by dropping a PDF
  on the EXE in Explorer.
- `<=10 MB` no-op: a 1,364-byte synthetic PDF produced no output. Its SHA-256
  remained `011BD372EDFA4643F3EB808C2FD6E1255554B649A82E9D7707603E564E6239AF`.
- Oversized image-heavy case: a repository-safe 33,763,068-byte synthetic PDF
  was fitted to 9,967,651 bytes. Existing `oversized-fit.pdf` and
  `oversized-fit-2.pdf` forced the final run to select `oversized-fit-3.pdf`.
- Immutability: the source remained 33,763,068 bytes with SHA-256
  `F4BBDB8DD9D4A135540C16E4DA352AAA54568855A0D280C80A30F7AF8CF2F07D`;
  the pre-existing destination remained 1,364 bytes with the no-op hash above.
- Output validation: pypdf 5.9.0 and PDFium 126.0.6462.0 each reopened all
  three pages; PDFium rendered all pages at 596x842. The output SHA-256 was
  `61327380F73168C12BA60D1988445175FD4EE840CE145E2576A99274621520E5`.
- Network independence: no TCP connection owned by the process was observed
  during startup, no-op, or oversized processing. All inputs and runtime
  components were local and no runtime download occurred.

Only repository-generated synthetic PDFs were used. No private or municipal
PDF or content was used or added to the repository.

The unchanged application source was also revalidated with the full Windows
test suite: 144 passed, 0 failed, 0 errors, 0 skipped in 121.188 seconds on
CPython 3.12.10.
