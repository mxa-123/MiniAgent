@echo off
REM 只做 Win7 兼容性检查，不重新打包。
REM 改完源码后先跑这个，确认没有引入 3.8+ 语法/API。
chcp 65001 >nul
cd /d "%~dp0"
python check_win7_compat.py %*
pause
