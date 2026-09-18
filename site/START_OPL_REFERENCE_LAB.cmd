@echo off
setlocal
cd /d "%~dp0"
title OpenPhysiologyLab ECG Reference Lab
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0local_server.ps1"
if errorlevel 1 (
  echo.
  echo The local OPL server could not start.
  pause
)
