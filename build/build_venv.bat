@echo off
REM ============================================================
REM Step 1: create venv with the STANDARD CPython (py -3.13).
REM IMPORTANT: do NOT use the bare "python" on PATH: on some
REM machines it is a stripped interpreter without tkinter.
REM ============================================================
setlocal
set ROOT=%~dp0..
echo [1/3] Creating venv at %ROOT%\.venv
py -3.13 -m venv "%ROOT%\.venv"
if errorlevel 1 goto :fail

set PY=%ROOT%\.venv\Scripts\python.exe
echo [2/3] Verifying tkinter
"%PY%" -c "import sys,tkinter;print(sys.executable);print('Tk',tkinter.TkVersion)"
if errorlevel 1 goto :fail

echo [3/3] Installing pinned dependencies
"%PY%" -m pip install --disable-pip-version-check -r "%ROOT%\requirements.txt"
if errorlevel 1 goto :fail

echo OK. Now run build_exe.bat
exit /b 0
:fail
echo FAILED. See README.md "interpreter trap" section.
exit /b 1
