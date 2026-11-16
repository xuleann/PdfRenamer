@echo off
REM ============================================================
REM Step 3: build the setup.exe installer with Inno Setup 6.
REM Output: <project-root>\dist\PdfRenamer_setup.exe
REM ============================================================
setlocal
set ROOT=%~dp0..
set ISCC=%~dp0innosetup\ISCC.exe

if not exist "%ISCC%" (
  echo Inno Setup compiler missing at %ISCC%
  echo Run get_innosetup.bat first, or use the offline fallback setup_bootstrap.py
  exit /b 1
)
if not exist "%ROOT%\dist\PdfRenamer.exe" (
  echo Portable exe missing. Run build_exe.bat first.
  exit /b 1
)

"%ISCC%" "%~dp0installer.iss"
if errorlevel 1 goto :fail
echo OK -^> %ROOT%\dist\PdfRenamer_setup.exe
exit /b 0
:fail
echo SETUP BUILD FAILED
exit /b 1
