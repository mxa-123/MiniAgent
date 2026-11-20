@echo off
REM Legacy build: pack the CLI entry into a single exe.
REM For the desktop window installer, use installer\build_installer.bat instead.
REM For Windows 7 targets use PyInstaller 4.x (works with Python 3.8).
REM Keep this file pure ASCII: the Win7 GBK console garbles Chinese text.
chcp 936 >nul
cd /d "%~dp0"
set PYINSTALLER_VER=pyinstaller==4.10

echo === MiniAgent build ===
python -m pip install %PYINSTALLER_VER%
if errorlevel 1 (
  echo [X] pip install failed.
  pause
  exit /b 1
)

python -m PyInstaller --onefile --name miniagent --clean run.py
if errorlevel 1 (
  echo [X] build failed.
  pause
  exit /b 1
)

echo [*] exe: dist\miniagent.exe
echo [*] copy config\config.example.json next to the exe as config\config.json if needed
pause
