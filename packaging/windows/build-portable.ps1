param(
    [Parameter(Mandatory = $true)]
    [string]$PythonExe,
    [string]$SourceCommit = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repoRoot

function Invoke-NativeChecked {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,
        [Parameter(Mandatory = $true)]
        [string]$FailureMessage
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage (exit=$LASTEXITCODE)"
    }
}

if ([string]::IsNullOrWhiteSpace($SourceCommit)) {
    $SourceCommit = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($SourceCommit)) {
        throw "Unable to resolve the current HEAD as the source commit."
    }
}

$resolvedSourceCommit = (& git rev-parse "$SourceCommit^{commit}").Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($resolvedSourceCommit)) {
    throw "Source commit is not available: $SourceCommit"
}
$SourceCommit = $resolvedSourceCommit
$shortSourceCommit = $SourceCommit.Substring(0, [Math]::Min(7, $SourceCommit.Length))

$sourceInputs = @(
    "src",
    "pyproject.toml",
    "packaging/windows",
    "THIRD_PARTY_NOTICES.txt",
    "licenses"
)
& git diff --quiet $SourceCommit -- @sourceInputs
if ($LASTEXITCODE -ne 0) {
    throw "Build inputs differ from the requested source commit."
}

$buildVenv = Join-Path $repoRoot ".portable-build-venv"
if (-not (Test-Path -LiteralPath $buildVenv)) {
    Invoke-NativeChecked -FailureMessage "Failed to create portable build virtual environment" -Command {
        & $PythonExe -m venv $buildVenv
    }
}
$buildPython = Join-Path $buildVenv "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $buildPython)) {
    throw "Portable build Python is missing: $buildPython"
}

$pythonIdentity = (& $buildPython -c "import platform, struct, sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}|{struct.calcsize(chr(80))*8}|{platform.machine()}')").Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Failed to identify portable build Python."
}
if ($pythonIdentity -ne "3.12.10|64|AMD64") {
    throw "Portable build requires CPython 3.12.10 x64; found $pythonIdentity"
}

Invoke-NativeChecked -FailureMessage "Failed to install pinned pip" -Command {
    & $buildPython -m pip install --upgrade pip==26.2.1
}
Invoke-NativeChecked -FailureMessage "Failed to install pinned portable build requirements" -Command {
    & $buildPython -m pip install -r packaging\windows\requirements-portable-build.txt
}

$pyinstaller = Join-Path $buildVenv "Scripts\pyinstaller.exe"
Invoke-NativeChecked -FailureMessage "PyInstaller build failed" -Command {
    & $pyinstaller --noconfirm --clean packaging\windows\pdf-size-fit.spec
}

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
    "PowerShell: $($PSVersionTable.PSVersion)"
    "Packager: PyInstaller 6.22.2 onedir"
    "Python runtime: CPython 3.12.10 x64"
    "Tcl/Tk runtime: 8.6.15"
    "PDFium runtime: 126.0.6462.0"
    "TkDND native payload: 2.10.1 x64 (as named by tkinterdnd2 0.6.2)"
    ""
    "Native/binary files (relative path | bytes | SHA-256 | file version):"
)
$artifactPrefix = $artifactDir.TrimEnd('\') + '\'
foreach ($file in $nativeFiles) {
    if (-not $file.FullName.StartsWith($artifactPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Inventory path escaped artifact directory: $($file.FullName)"
    }
    $relative = $file.FullName.Substring($artifactPrefix.Length)
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash
    $version = $file.VersionInfo.FileVersion
    $inventory += "$relative | $($file.Length) | $hash | $version"
}
$inventory += ""
$inventory += "Tcl/Tk data: _internal\_tcl_data and _internal\_tk_data"
$inventory += "TkDND data: _internal\tkinterdnd2\tkdnd\win-x64"
$inventory += "Python bytecode library: _internal\base_library.zip"
$inventory | Set-Content -LiteralPath $inventoryPath -Encoding utf8

$zipPath = Join-Path $repoRoot "dist\pdf-size-fit-win-x64-source-$shortSourceCommit.zip"
Compress-Archive -LiteralPath $artifactDir -DestinationPath $zipPath -CompressionLevel Optimal -Force
$zipHash = Get-FileHash -Algorithm SHA256 -LiteralPath $zipPath
Write-Output "Source commit: $SourceCommit"
Write-Output "Artifact: $zipPath"
Write-Output "Bytes: $((Get-Item -LiteralPath $zipPath).Length)"
Write-Output "SHA256: $($zipHash.Hash)"
