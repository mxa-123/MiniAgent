; MiniAgent Win7/Win8.1 32-bit installer
; Unicode NSIS 3, ASCII-only source. Build with:
;   makensis /DMINIAGENT_STAGE="E:\AI\vm_stuff\MiniAgent-win32-build" \
;            /DMINIAGENT_OUTPUT="E:\AI\vm_stuff\MiniAgent_src\dist\MiniAgent-Win7-32位安装包.exe" \
;            installer\MiniAgent-Win7-x86.nsi
;
; Targets: Windows 7 SP1 (32/64-bit), Windows 8/8.1 (32/64-bit), Windows 10/11 x86
; Runtime: bundled Python 3.7.9 win32 + tkinter (no system Python required)

Unicode true
!include "MUI2.nsh"

Name "MiniAgent (Win7 32-bit)"
!ifdef MINIAGENT_OUTPUT
  OutFile "${MINIAGENT_OUTPUT}"
!else
  OutFile "..\dist\MiniAgent-Win7-x86-Setup.exe"
!endif

InstallDir "$LOCALAPPDATA\MiniAgent"
RequestExecutionLevel user
SetCompressor /SOLID lzma

!define APPNAME "MiniAgent"
!define APPVERSION "0.1.0"
!define UNINSTKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\MiniAgentWin7x86"

VIProductVersion "0.1.0.0"
VIAddVersionKey "ProductName" "MiniAgent Win7 x86"
VIAddVersionKey "FileVersion" "0.1.0"
VIAddVersionKey "FileDescription" "MiniAgent for Win7 / Win8.1 (32-bit)"

!define MUI_ABORTWARNING
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\packaging\LICENSE.txt"
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

; ---- helper: set env + launch via pythonw ----
!macro WRITE_LAUNCHER PATH
  SetOutPath "$INSTDIR"
  FileOpen $0 "${PATH}" w
  FileWrite $0 '@echo off$\r$\n'
  FileWrite $0 'chcp 65001 >nul$\r$\n'
  FileWrite $0 'cd /d "$INSTDIR"$\r$\n'
  FileWrite $0 'set "TCL_LIBRARY=$INSTDIR\python\tcl\tcl8.6"$\r$\n'
  FileWrite $0 'set "TK_LIBRARY=$INSTDIR\python\tcl\tk8.6"$\r$\n'
  FileWrite $0 'start "" "$INSTDIR\python\pythonw.exe" "$INSTDIR\desktop.py"$\r$\n'
  FileClose $0
!macroend

Section "MiniAgent" SecMain
  SetOutPath "$INSTDIR"

  ; bundled 32-bit runtime + app
  File /r "${MINIAGENT_STAGE}\python"
  File "${MINIAGENT_STAGE}\desktop.py"
  File "${MINIAGENT_STAGE}\run.py"
  File "${MINIAGENT_STAGE}\vc_redist.x86.exe"

  SetOutPath "$INSTDIR\miniagent"
  File "${MINIAGENT_STAGE}\miniagent\*.py"
  SetOutPath "$INSTDIR\config"
  File "${MINIAGENT_STAGE}\config\*.*"
  SetOutPath "$INSTDIR\plugins"
  File "${MINIAGENT_STAGE}\plugins\*.py"
  SetOutPath "$INSTDIR\skills"
  File "${MINIAGENT_STAGE}\skills\*.*"

  SetOutPath "$INSTDIR"
  ; launchers
  !insertmacro WRITE_LAUNCHER "$INSTDIR\MiniAgent.bat"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  ; register (HKCU, no UAC)
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayName" "MiniAgent (Win7 32-bit)"
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayVersion" "${APPVERSION}"
  WriteRegStr HKCU "${UNINSTKEY}" "Publisher" "MiniAgent"
  WriteRegStr HKCU "${UNINSTKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINSTKEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayIcon" "$INSTDIR\python\pythonw.exe"
  WriteRegDWORD HKCU "${UNINSTKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINSTKEY}" "NoRepair" 1

  ; shortcuts
  CreateDirectory "$SMPROGRAMS\MiniAgent"
  CreateShortCut "$DESKTOP\MiniAgent.lnk" "$INSTDIR\MiniAgent.bat" "" "$INSTDIR\python\pythonw.exe" 0
  CreateShortCut "$SMPROGRAMS\MiniAgent\MiniAgent.lnk" "$INSTDIR\MiniAgent.bat" "" "$INSTDIR\python\pythonw.exe" 0
  CreateShortCut "$SMPROGRAMS\MiniAgent\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\MiniAgent.lnk"
  Delete "$SMPROGRAMS\MiniAgent\MiniAgent.lnk"
  Delete "$SMPROGRAMS\MiniAgent\Uninstall.lnk"
  RMDir "$SMPROGRAMS\MiniAgent"

  Delete "$INSTDIR\MiniAgent.bat"
  Delete "$INSTDIR\desktop.py"
  Delete "$INSTDIR\run.py"
  Delete "$INSTDIR\vc_redist.x86.exe"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir /r "$INSTDIR\miniagent"
  RMDir /r "$INSTDIR\config"
  RMDir /r "$INSTDIR\plugins"
  RMDir /r "$INSTDIR\skills"
  RMDir /r "$INSTDIR\python"
  RMDir "$INSTDIR"

  DeleteRegKey HKCU "${UNINSTKEY}"
SectionEnd
