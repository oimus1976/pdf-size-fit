@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"

if "%~1"=="" (
  echo Usage: build-portable.cmd ^<PythonExe^> [SourceCommit]
  exit /b 2
)

set "PYTHON_EXE=%~1"
set "SOURCE_COMMIT=%~2"

if not exist "%PYTHON_EXE%" (
  echo ERROR: Python executable not found: %PYTHON_EXE%
  exit /b 2
)

for /f %%I in ('powershell.exe -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "STAMP=%%I"
set "LOG_DIR=%REPO_ROOT%\logs\verification"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1
set "LOG=%LOG_DIR%\issue-13-final-portable-build-%STAMP%.log"
set "BUILD_LOG=%LOG%"

>"%LOG%" echo PDF Size Fit portable build
>>"%LOG%" echo Launcher: packaging\windows\build-portable.cmd
>>"%LOG%" echo Python: %PYTHON_EXE%
if not "%SOURCE_COMMIT%"=="" >>"%LOG%" echo Requested source commit: %SOURCE_COMMIT%
>>"%LOG%" echo Started: %DATE% %TIME%
>>"%LOG%" echo.

echo Building portable artifact...
echo Detailed output: %LOG%

if "%SOURCE_COMMIT%"=="" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%build-portable.ps1" -PythonExe "%PYTHON_EXE%" >>"%LOG%" 2>&1
) else (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%build-portable.ps1" -PythonExe "%PYTHON_EXE%" -SourceCommit "%SOURCE_COMMIT%" >>"%LOG%" 2>&1
)
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
  echo.
  echo BUILD FAILED ^(exit=%RC%^)
  echo Log: %LOG%
  echo --- last 30 log lines ---
  powershell.exe -NoProfile -Command "Get-Content -LiteralPath $env:BUILD_LOG -Tail 30"
  exit /b %RC%
)

echo.
echo BUILD SUCCEEDED
findstr /B /C:"Source commit:" /C:"Artifact:" /C:"Bytes:" /C:"SHA256:" "%LOG%"
echo Log: %LOG%
exit /b 0
