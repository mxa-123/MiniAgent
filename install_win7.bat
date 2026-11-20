@echo off
REM MiniAgent setup for Windows 7 / 8.1 (source mode, needs Python 3.8.10)
REM Win7 needs Python 3.8.10 (last version supporting Windows 7).
REM NOTE: the setup EXE in dist\ is 64-bit Win8+/Win10/Win11 only, NOT for Win7.
REM Keep this file pure ASCII: the Win7 GBK console garbles Chinese text.
chcp 936 >nul
cd /d "%~dp0"
echo === MiniAgent setup ===

where python >nul 2>nul
if errorlevel 1 (
  echo [X] Python not found.
  echo     Win7 : install Python 3.8.10  https://www.python.org/downloads/release/python-3810/
  echo     Win8+: Python 3.8 ~ 3.12 both fine
  pause
  exit /b 1
)

python -c "import sys; print('Python', sys.version)"
if errorlevel 1 (
  echo [X] Python is broken.
  pause
  exit /b 1
)

echo [*] installing optional dependency: requests
python -m pip install requests

echo [*] generating default config
python run.py --init

echo [*] setup done.
echo [*] config file: %USERPROFILE%\.miniagent\config.json
echo [*] next: run.bat [desktop window] / run_web.bat [browser] / run_cli.bat [CLI]
echo [*] If the window does not appear, run run_debug.bat
pause
