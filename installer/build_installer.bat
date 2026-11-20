@echo off
chcp 936 >nul
cd /d "%~dp0"
REM Build the MiniAgent setup EXE into the project dist\ folder.
REM Output: dist\MiniAgent-Setup.exe renamed to a Chinese setup name.
REM Keep this file pure ASCII: the Win7 GBK console garbles Chinese text.
echo === MiniAgent installer build ===
python build_installer.py
if errorlevel 1 (
  echo [X] build failed. Read the messages above.
  pause
  exit /b 1
)
echo [*] done. Look in the dist\ folder of the project root.
pause
