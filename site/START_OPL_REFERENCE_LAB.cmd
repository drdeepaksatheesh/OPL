@echo off
setlocal
cd /d "%~dp0"
title OpenPhysiologyLab ECG Reference Lab

echo.
echo OpenPhysiologyLab ECG Reference Lab
echo -----------------------------------
echo.

if not exist "%~dp0local_server.ps1" (
  echo ERROR: local_server.ps1 is missing.
  echo.
  echo This usually means the launcher was run from inside the ZIP.
  echo Please right-click the ZIP, choose Extract All, open the extracted folder,
  echo and then double-click START_OPL_REFERENCE_LAB.cmd.
  echo.
  pause
  exit /b 1
)

if not exist "%~dp0reference\ecg-id\index.html" (
  echo ERROR: the ECG Reference Lab files are incomplete.
  echo.
  echo Please extract the entire ZIP before running OPL.
  echo.
  pause
  exit /b 1
)

echo Starting OPL...
echo If startup fails, this window will remain open so the error can be read.
echo A copy of the startup output will also be written to OPL_STARTUP_LOG.txt.
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -NoExit -Command ^
  "$ErrorActionPreference='Stop'; $log=Join-Path '%~dp0' 'OPL_STARTUP_LOG.txt'; try { & '%~dp0local_server.ps1' 2>&1 | Tee-Object -FilePath $log } catch { $_ | Out-String | Tee-Object -FilePath $log -Append; Write-Host ''; Write-Host 'OPL STARTUP FAILED' -ForegroundColor Red; Write-Host $_.Exception.Message -ForegroundColor Red; Write-Host ''; Write-Host ('Error log: ' + $log) -ForegroundColor Yellow }"
