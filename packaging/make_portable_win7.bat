@echo off
REM 生成 Win7 兼容版便携包（内置 Python 3.7.9，不需要 KB2533623 补丁）
REM 输出: build\MiniAgent-portable-win7\  和  dist\MiniAgent-portable-win7.zip
chcp 65001 >nul
cd /d "%~dp0"
python prepare_win7.py %*
echo.
echo ===== 接着做兼容性检查 =====
python check_win7_compat.py
pause
