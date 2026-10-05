@echo off
setlocal
cd /d "%~dp0"
title OpenPhysiologyLab ECG Reference Lab

if not exist "%~dp0START_OPL_REFERENCE_LAB.ps1" (
  echo.
  echo ERROR: START_OPL_REFERENCE_LAB.ps1 is missing.
  echo Please extract the entire ZIP before running OPL.
  echo.
  pause
  exit /b 1
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0START_OPL_REFERENCE_LAB.ps1"
set "rc=%ERRORLEVEL%"

if not "%rc%"=="0" (
  echo.
  echo OPL exited with error code %rc%.
  echo See OPL_STARTUP_LOG.txt in this folder.
  echo.
  pause
)

exit /b %rc%
