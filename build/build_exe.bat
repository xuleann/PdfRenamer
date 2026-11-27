@echo off
REM ============================================================
REM Step 2: build the portable single-file exe with PyInstaller.
REM Output: <project-root>\dist\PdfRenamer.exe
REM ============================================================
setlocal
set ROOT=%~dp0..
set PY=%ROOT%\.venv\Scripts\python.exe

if not exist "%PY%" (
  echo venv missing. Run build_venv.bat first.
  exit /b 1
)

echo [1/4] Static no-AI gate
"%PY%" "%ROOT%\tests\scan_no_ai.py"
if errorlevel 1 goto :fail

echo [2/4] Generating icon
"%PY%" "%ROOT%\build\make_icon.py"
if errorlevel 1 goto :fail

echo [3/4] Exporting default config
"%PY%" -c "import sys;sys.path.insert(0,r'%ROOT%\src');from pdfrenamer.config import export_defaults;from pathlib import Path;export_defaults(Path(r'%ROOT%\config\default_config.json'))"
if errorlevel 1 goto :fail

echo [4/4] PyInstaller (full spec: includes RapidOCR/ONNXRuntime for handwriting OCR)
"%PY%" -m PyInstaller --clean --noconfirm --distpath "%ROOT%\dist" --workpath "%ROOT%\build\work" "%~dp0PdfRenamer_full.spec"
if errorlevel 1 goto :fail

echo OK -^> %ROOT%\dist\PdfRenamer.exe
exit /b 0
:fail
echo BUILD FAILED
exit /b 1
