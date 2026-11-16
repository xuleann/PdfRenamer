@echo off
REM ============================================================
REM Download Inno Setup 6.7.4 and install it into build\innosetup.
REM Only needed if build\innosetup\ISCC.exe is missing.
REM ============================================================
setlocal
set DEST=%~dp0innosetup-6.7.4.exe
echo Downloading Inno Setup 6.7.4 ...
curl -sL -o "%DEST%" "https://github.com/jrsoftware/issrc/releases/download/is-6_7_4/innosetup-6.7.4.exe"
if errorlevel 1 goto :fail
echo Installing silently into %~dp0innosetup ...
start /wait "" "%DEST%" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /NOICONS "/DIR=%~dp0innosetup"
if not exist "%~dp0innosetup\ISCC.exe" goto :fail
echo OK. Now run make_setup.bat
exit /b 0
:fail
echo Download/install failed. You can still use the offline fallback:
echo   .venv\Scripts\python.exe -m PyInstaller --onefile --noconsole --add-data "dist\PdfRenamer.exe;." build\setup_bootstrap.py
echo   (see README.md section 3)
exit /b 1
