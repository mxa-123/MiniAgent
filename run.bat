@echo off
chcp 936 >nul
cd /d "%~dp0"
REM MiniAgent desktop window - default entry.
REM Browser UI: run_web.bat   Command line: run_cli.bat   Debug: run_debug.bat
REM Keep this file pure ASCII: the Win7 GBK console garbles Chinese text.
REM cd /d is required so the script works even when started from C:\Windows\System32.

set "PYEXE="
REM Some Python installs on PATH have no tkinter; pick the first one that can
REM actually open a window, instead of blindly using the first "where python".
for /f "delims=" %%i in ('where python 2^>nul') do (
  if not defined PYEXE (
    "%%i" -c "import tkinter, miniagent.runtime" >nul 2>&1
    if not errorlevel 1 set "PYEXE=%%i"
  )
)
if not defined PYEXE (
  echo [X] No Python with tkinter was found in PATH.
  echo     Install Python 3.8 or newer, or use the setup EXE in dist.
  echo     Run run_debug.bat for details.
  pause
  exit /b 1
)

set "PYDIR="
for /f "delims=" %%i in ("%PYEXE%") do set "PYDIR=%%~dpi"
set "PYW=%PYDIR%pythonw.exe"

if exist "%PYW%" (
  start "" "%PYW%" desktop.py
  echo [*] MiniAgent window is starting.
  echo [*] If nothing appears, read: %USERPROFILE%\.miniagent\desktop.log
  exit /b 0
)

echo [!] pythonw.exe not found; falling back to python.exe; console stays open.
"%PYEXE%" desktop.py
if errorlevel 1 (
  echo [X] MiniAgent failed. See %USERPROFILE%\.miniagent\desktop.log
  pause
  exit /b 1
)
