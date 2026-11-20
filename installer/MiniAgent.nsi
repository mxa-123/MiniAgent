; ============================================================
;  MiniAgent setup (NSIS 3, Unicode, ASCII-only source)
;  Install to %LOCALAPPDATA%\MiniAgent, HKCU registry, no UAC.
;  Build:  installer\build_installer.bat
;
;  COMPATIBILITY NOTE (important):
;    PyInstaller 6.x + Python 3.14 produce 64-bit binaries that require
;    Windows 8 / 10 / 11. They do NOT run on Windows 7 or on 32-bit Windows.
;    Win7 / 32-bit build path (not used by this script):
;      use Python 3.8.10 (32-bit) + PyInstaller 4.10, then compile this
;      same .nsi; the resulting installer targets Win7 x86.
;    Define MINIAGENT_SOURCE_MODE to ship the source instead of the frozen
;    exe (used automatically when PyInstaller is unavailable).
; ============================================================

Unicode true
!include "MUI2.nsh"

Name "MiniAgent"
!ifdef MINIAGENT_OUTFILE
  OutFile "${MINIAGENT_OUTFILE}"
!else
  OutFile "..\dist\MiniAgent-Setup.exe"
!endif
InstallDir "$LOCALAPPDATA\MiniAgent"
RequestExecutionLevel user
SetCompressor /SOLID lzma

!define APPNAME "MiniAgent"
!define APPVERSION "0.1.0"
!define UNINSTKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\MiniAgent"

VIProductVersion "0.1.0.0"
VIAddVersionKey "ProductName" "MiniAgent"
VIAddVersionKey "FileVersion" "0.1.0"
VIAddVersionKey "LegalCopyright" "MiniAgent"
VIAddVersionKey "FileDescription" "MiniAgent Setup"

!define MUI_ABORTWARNING
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

; ------------------------------------------------------------
;  Source-mode fallback: check that Python is on the target PC.
; ------------------------------------------------------------
!ifdef MINIAGENT_SOURCE_MODE
Function .onInit
  nsExec::Exec 'cmd /c where pythonw >nul 2>nul'
  Pop $0
  StrCmp $0 0 _python_ok
    MessageBox MB_OK|MB_ICONEXCLAMATION \
      "This build needs Python 3.8 or newer (pythonw.exe on PATH).$\n$\nInstall Python first if you have not done so."
_python_ok:
FunctionEnd
!endif

; ------------------------------------------------------------
Section "MiniAgent" SecMain
  SetOutPath "$INSTDIR"

  !ifdef MINIAGENT_SOURCE_MODE
    File "..\run.py"
    File "..\desktop.py"
    File "RunMiniAgent.bat"
    SetOutPath "$INSTDIR\miniagent"
    File "..\miniagent\*.py"
  !else
    File "..\dist\MiniAgent.exe"
  !endif

  SetOutPath "$INSTDIR\config"
  File "..\config\config.example.json"
  SetOutPath "$INSTDIR\skills"
  File "..\skills\*.*"
  SetOutPath "$INSTDIR\plugins"
  File "..\plugins\*.*"
  SetOutPath "$INSTDIR"
  File "..\README.md"

  WriteUninstaller "$INSTDIR\Uninstall.exe"

  WriteRegStr HKCU "${UNINSTKEY}" "DisplayName" "MiniAgent"
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayVersion" "${APPVERSION}"
  WriteRegStr HKCU "${UNINSTKEY}" "Publisher" "MiniAgent"
  WriteRegStr HKCU "${UNINSTKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINSTKEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegDWORD HKCU "${UNINSTKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINSTKEY}" "NoRepair" 1
  !ifdef MINIAGENT_SOURCE_MODE
    WriteRegStr HKCU "${UNINSTKEY}" "DisplayIcon" "$INSTDIR\RunMiniAgent.bat"
  !else
    WriteRegStr HKCU "${UNINSTKEY}" "DisplayIcon" "$INSTDIR\MiniAgent.exe"
  !endif

  CreateDirectory "$SMPROGRAMS\MiniAgent"
  !ifdef MINIAGENT_SOURCE_MODE
    CreateShortCut "$DESKTOP\MiniAgent.lnk" "$INSTDIR\RunMiniAgent.bat"
    CreateShortCut "$SMPROGRAMS\MiniAgent\MiniAgent.lnk" "$INSTDIR\RunMiniAgent.bat"
  !else
    CreateShortCut "$DESKTOP\MiniAgent.lnk" "$INSTDIR\MiniAgent.exe" "" "$INSTDIR\MiniAgent.exe" 0
    CreateShortCut "$SMPROGRAMS\MiniAgent\MiniAgent.lnk" "$INSTDIR\MiniAgent.exe" "" "$INSTDIR\MiniAgent.exe" 0
  !endif
  CreateShortCut "$SMPROGRAMS\MiniAgent\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
SectionEnd

; ------------------------------------------------------------
Section "Uninstall"
  Delete "$DESKTOP\MiniAgent.lnk"
  Delete "$SMPROGRAMS\MiniAgent\MiniAgent.lnk"
  Delete "$SMPROGRAMS\MiniAgent\Uninstall.lnk"
  RMDir "$SMPROGRAMS\MiniAgent"

  Delete "$INSTDIR\MiniAgent.exe"
  Delete "$INSTDIR\RunMiniAgent.bat"
  Delete "$INSTDIR\Uninstall.exe"
  Delete "$INSTDIR\README.md"
  Delete "$INSTDIR\run.py"
  Delete "$INSTDIR\desktop.py"
  Delete "$INSTDIR\miniagent\*.py"
  RMDir "$INSTDIR\miniagent"
  Delete "$INSTDIR\config\config.example.json"
  RMDir "$INSTDIR\config"
  Delete "$INSTDIR\skills\*.*"
  RMDir "$INSTDIR\skills"
  Delete "$INSTDIR\plugins\*.*"
  RMDir "$INSTDIR\plugins"
  RMDir "$INSTDIR"

  DeleteRegKey HKCU "${UNINSTKEY}"
  ; NOTE: user settings under %USERPROFILE%\.miniagent are intentionally kept.
SectionEnd
