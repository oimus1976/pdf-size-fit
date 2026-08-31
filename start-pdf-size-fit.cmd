@echo off
setlocal

set "APP_ROOT=%~dp0"
set "APP_PYTHON=%APP_ROOT%.venv\Scripts\python.exe"
set "APP_PYTHONW=%APP_ROOT%.venv\Scripts\pythonw.exe"

if not exist "%APP_PYTHON%" goto :missing_runtime
if not exist "%APP_PYTHONW%" goto :missing_runtime

"%APP_PYTHON%" -c "import pdf_size_fit.gui" >nul 2>&1
if errorlevel 1 goto :missing_package

start "PDF Size Fit" "%APP_PYTHONW%" -m pdf_size_fit.gui
exit /b 0

:missing_runtime
echo PDF Size Fit could not start because .venv\Scripts\pythonw.exe is missing.
echo Follow the Windows GUI setup steps in README.md, then try again.
pause
exit /b 1

:missing_package
echo PDF Size Fit could not start because the project or its dependencies are not installed.
echo Run: .venv\Scripts\python.exe -m pip install -e ".[dev]"
echo Then double-click this launcher again.
pause
exit /b 1
