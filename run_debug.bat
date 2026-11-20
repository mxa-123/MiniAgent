@echo off
chcp 936 >nul
cd /d "%~dp0"
REM Debug console for MiniAgent: shows every error and keeps the window open.
REM Use this when the desktop window does not appear after double-clicking run.bat.
REM Keep this file pure ASCII: the Win7 GBK console garbles Chinese text.
echo === MiniAgent debug console ===
echo [*] folder : %CD%
echo [*] log    : %USERPROFILE%\.miniagent\desktop.log
echo.

set "PYEXE="
for /f "delims=" %%i in ('where python 2^>nul') do (
  if not defined PYEXE (
    "%%i" -c "import tkinter, miniagent.runtime" >nul 2>&1
    if not errorlevel 1 set "PYEXE=%%i"
  )
)
if not defined PYEXE (
  echo [X] No Python with tkinter was found in PATH.
  echo     Install Python 3.8 or newer, or use the setup EXE in dist.
  pause
  exit /b 1
)

"%PYEXE%" desktop.py
echo.
echo [*] exit code: %errorlevel%
echo [*] If the window did not appear, open the log file shown above.
pause
