; ============================================================
;  MiniAgent（灵枢）安装包  ——  NSIS (Unicode)
;  自带 Python 3.8 嵌入式运行时，目标机零依赖（Win7/8.1/10/11 64 位）
;  构建：在 packaging\ 目录运行  makensis MiniAgent.nsi
; ============================================================
Unicode true
!include "MUI2.nsh"
!include "WinVer.nsh"

; ---------- 基本信息 ----------
Name "MiniAgent（灵枢）"
OutFile "dist\MiniAgent-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\MiniAgent"
InstallDirRegKey HKCU "Software\MiniAgent" "InstallDir"
RequestExecutionLevel user        ; 不需要管理员，兼容受限制的 Win7 账户
SetCompressor /SOLID lzma

VIProductVersion "0.1.0.0"
VIAddVersionKey "ProductName" "MiniAgent"
VIAddVersionKey "FileVersion" "0.1.0"
VIAddVersionKey "LegalCopyright" "MiniAgent"
VIAddVersionKey "FileDescription" "MiniAgent 安装程序"

; ---------- MUI 页面 ----------
!define MUI_ABORTWARNING
!define MUI_ICON "assets\miniagent.ico"
!define MUI_UNICON "assets\miniagent.ico"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_FUNCTION "LaunchWeb"
!define MUI_FINISHPAGE_RUN_TEXT "启动 MiniAgent 网页版"
!define MUI_FINISHPAGE_SHOWREADME
!define MUI_FINISHPAGE_SHOWREADME_TEXT "创建桌面快捷方式"
!define MUI_FINISHPAGE_SHOWREADME_FUNCTION "CreateDesktopShortcut"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"

; ---------- 安装段 ----------
Section "Main" SecMain
  SetOutPath "$INSTDIR"
  File /r "build\app\*"              ; 应用文件（run.py / miniagent / config / plugins / skills）
  File "assets\miniagent.ico"

  SetOutPath "$INSTDIR\python"
  File /r "build\runtime\*"          ; 嵌入式 Python 3.8 运行时

  ; 记录安装位置（供重装/卸载定位）
  WriteRegStr HKCU "Software\MiniAgent" "InstallDir" "$INSTDIR"

  ; 首次生成默认配置到用户目录 ~/.miniagent
  nsExec::ExecToLog '"$INSTDIR\python\python.exe" "$INSTDIR\run.py" --init'

  ; 开始菜单
  CreateDirectory "$SMPROGRAMS\MiniAgent"
  CreateShortCut "$SMPROGRAMS\MiniAgent\MiniAgent 命令行.lnk" \
      "$INSTDIR\python\python.exe" '"$INSTDIR\run.py"' \
      "$INSTDIR" "$INSTDIR\miniagent.ico" 0
  CreateShortCut "$SMPROGRAMS\MiniAgent\MiniAgent 网页版.lnk" \
      "$INSTDIR\python\pythonw.exe" '"$INSTDIR\run.py" --web' \
      "$INSTDIR" "$INSTDIR\miniagent.ico" 0

  ; 卸载程序 + 注册表
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MiniAgent" \
      "DisplayName" "MiniAgent（灵枢）"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MiniAgent" \
      "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MiniAgent" \
      "DisplayIcon" "$INSTDIR\miniagent.ico"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MiniAgent" \
      "InstallLocation" "$INSTDIR"
SectionEnd

Function LaunchWeb
  Exec '"$INSTDIR\python\pythonw.exe" "$INSTDIR\run.py" --web'
FunctionEnd

Function CreateDesktopShortcut
  CreateShortCut "$DESKTOP\MiniAgent 网页版.lnk" \
      "$INSTDIR\python\pythonw.exe" '"$INSTDIR\run.py" --web' \
      "$INSTDIR" "$INSTDIR\miniagent.ico" 0
FunctionEnd

; ---------- 系统版本检查（至少 Win7）----------
Function .onInit
  ${IfNot} ${AtLeastWin7}
    MessageBox MB_OK|MB_ICONEXCLAMATION \
        "MiniAgent 需要 Windows 7 或更高版本。$\n当前系统不受支持，安装中止。"
    Abort
  ${EndIf}
FunctionEnd

; ---------- 卸载段 ----------
Section "Uninstall"
  Delete "$INSTDIR\Uninstall.exe"
  Delete "$INSTDIR\miniagent.ico"
  RMDir /r "$INSTDIR"
  Delete "$SMPROGRAMS\MiniAgent\MiniAgent 命令行.lnk"
  Delete "$SMPROGRAMS\MiniAgent\MiniAgent 网页版.lnk"
  RMDir "$SMPROGRAMS\MiniAgent"
  Delete "$DESKTOP\MiniAgent 网页版.lnk"
  DeleteRegKey HKCU "Software\MiniAgent"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MiniAgent"
SectionEnd
