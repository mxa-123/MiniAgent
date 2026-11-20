@echo off
chcp 936 >nul
cd /d "%~dp0"
REM MiniAgent command-line interface (advanced users / scripting).
REM For the graphical window, use run.bat instead.
REM Keep this file pure ASCII: the Win7 GBK console garbles Chinese text.
python run.py %*
pause
