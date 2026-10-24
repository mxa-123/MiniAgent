@echo off
REM ============================================================
REM  一键生成 MiniAgent 安装包（dist\MiniAgent-Setup.exe）
REM  在 packaging\ 目录运行。需要联网（首次下载 Python 3.8 运行时）
REM  并建议安装 NSIS（https://nsis.sourceforge.io/Download）
REM ============================================================
chcp 65001 >nul
cd /d "%~dp0"

echo === 1/2 准备运行时与应用文件 ===
python prepare.py
if errorlevel 1 (
  echo [X] 准备失败，请检查 Python 是否可用、网络是否连通。
  pause
  exit /b 1
)

echo === 2/2 生成安装包 ===
where makensis >nul 2>nul
if errorlevel 1 (
  echo.
  echo [!] 未找到 makensis（NSIS 编译器）。
  echo     请安装 NSIS: https://nsis.sourceforge.io/Download
  echo     安装后重新运行本脚本即可生成 dist\MiniAgent-Setup.exe
  echo.
  echo [提示] 不想装 NSIS？可直接用便携版：
  echo       python prepare.py --portable  ->  dist\MiniAgent-portable.zip
  echo       （解压即用，无需安装，照样能在 Win7 上跑）
  pause
  exit /b 2
)

makensis MiniAgent.nsi
if errorlevel 1 (
  echo [X] makensis 失败，请查看上方错误信息。
  pause
  exit /b 1
)

echo.
echo [*] 安装包已生成: dist\MiniAgent-Setup.exe
echo [*] 双击它即可在其它电脑上安装（无需预装 Python）。
pause
