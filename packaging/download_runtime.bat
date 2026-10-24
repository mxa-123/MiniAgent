@echo off
REM 仅下载并解压嵌入式 Python 3.8 运行时（build\runtime）。
chcp 65001 >nul
cd /d "%~dp0"
python prepare.py --runtime-only
pause
