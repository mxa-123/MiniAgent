@echo off
REM 生成便携版 ZIP（dist\MiniAgent-portable.zip），解压即用，无需安装。
chcp 65001 >nul
cd /d "%~dp0"
python prepare.py --portable
pause
