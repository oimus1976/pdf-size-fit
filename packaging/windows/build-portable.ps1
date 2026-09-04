param(
    [Parameter(Mandatory = $true)]
    [string]$PythonExe,
    [string]$SourceCommit = "1242df81e2a3bc6b0b00ddd9ef19595cb3fb548a"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repoRoot

& git cat-file -e "$SourceCommit^{commit}"
if ($LASTEXITCODE -ne 0) {
    throw "Source commit is not available: $SourceCommit"
}
& git diff --quiet $SourceCommit -- src pyproject.toml
if ($LASTEXITCODE -ne 0) {
    throw "Application source differs from the requested source commit."
}

$buildVenv = Join-Path $repoRoot ".portable-build-venv"
if (-not (Test-Path -LiteralPath $buildVenv)) {
    & $PythonExe -m venv $buildVenv
}
$buildPython = Join-Path $buildVenv "Scripts\python.exe"
& $buildPython -m pip install --upgrade pip==26.2.1
& $buildPython -m pip install -r packaging\windows\requirements-portable-build.txt

& (Join-Path $buildVenv "Scripts\pyinstaller.exe") --noconfirm --clean packaging\windows\pdf-size-fit.spec

$artifactDir = Join-Path $repoRoot "dist\pdf-size-fit"
if (-not (Test-Path -LiteralPath (Join-Path $artifactDir "pdf-size-fit.exe"))) {
    throw "PyInstaller artifact was not created."
}
Copy-Item -LiteralPath (Join-Path $repoRoot "THIRD_PARTY_NOTICES.txt") -Destination $artifactDir
Copy-Item -LiteralPath (Join-Path $repoRoot "licenses") -Destination $artifactDir -Recurse

$inventoryPath = Join-Path $artifactDir "RUNTIME_INVENTORY.txt"
$nativeFiles = Get-ChildItem -LiteralPath $artifactDir -Recurse -File |
    Where-Object { $_.Extension -in @(".exe", ".dll", ".pyd") } |
    Sort-Object FullName
$inventory = @(
    "PDF Size Fit runtime inventory"
    "Source commit: $SourceCommit"
    "Build OS: $([System.Environment]::OSVersion.VersionString)"
    "Architecture: $([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture)"
    "Packager: PyInstaller 6.22.2 onedir"
    "Python runtime: CPython 3.12.10 x64"
    "Tcl/Tk runtime: 8.6.15"
    "PDFium runtime: 126.0.6462.0"
    "TkDND native payload: 2.10.1 x64 (as named by tkinterdnd2 0.6.2)"
    ""
    "Native/binary files (relative path | bytes | SHA-256 | file version):"
)
foreach ($file in $nativeFiles) {
    $relative = [System.IO.Path]::GetRelativePath($artifactDir, $file.FullName)
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash
    $version = $file.VersionInfo.FileVersion
    $inventory += "$relative | $($file.Length) | $hash | $version"
}
$inventory += ""
$inventory += "Tcl/Tk data: _internal\_tcl_data and _internal\_tk_data"
$inventory += "TkDND data: _internal\tkinterdnd2\tkdnd\win-x64"
$inventory += "Python bytecode library: _internal\base_library.zip"
$inventory | Set-Content -LiteralPath $inventoryPath -Encoding utf8

$zipPath = Join-Path $repoRoot "dist\pdf-size-fit-win-x64-source-1242df8.zip"
Compress-Archive -LiteralPath $artifactDir -DestinationPath $zipPath -CompressionLevel Optimal -Force
$zipHash = Get-FileHash -Algorithm SHA256 -LiteralPath $zipPath
Write-Output "Artifact: $zipPath"
Write-Output "Bytes: $((Get-Item -LiteralPath $zipPath).Length)"
Write-Output "SHA256: $($zipHash.Hash)"
