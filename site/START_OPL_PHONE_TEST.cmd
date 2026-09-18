@echo off
setlocal
cd /d "%~dp0"
title OpenPhysiologyLab Phone Test
echo.
echo OpenPhysiologyLab - phone test mode
echo This deliberately exposes the local test server to your current LAN.
echo Use only on a trusted home/institutional network.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0local_server.ps1" -AllowLan
if errorlevel 1 (
  echo.
  echo The local OPL phone-test server could not start.
  pause
)
