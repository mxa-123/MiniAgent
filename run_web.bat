@echo off
chcp 936 >nul
cd /d "%~dp0"
REM MiniAgent browser interface (opens a local web page in your browser).
REM For the desktop window, use run.bat instead.
REM Keep this file pure ASCII: the Win7 GBK console garbles Chinese text.
python run.py --web %*
pause
