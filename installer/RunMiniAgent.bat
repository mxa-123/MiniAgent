@echo off
chcp 936 >nul
cd /d "%~dp0"
REM Source-mode launcher: needs Python 3.8 or newer installed on this PC.
REM The setup EXE built in bundled mode does NOT use this file.
REM Keep this file pure ASCII: the Win7 GBK console garbles Chinese text.
where pythonw >nul 2>nul
if errorlevel 1 (
  echo [X] pythonw.exe not found. Please install Python 3.8 or newer.
  pause
  exit /b 1
)
start "" pythonw desktop.py
