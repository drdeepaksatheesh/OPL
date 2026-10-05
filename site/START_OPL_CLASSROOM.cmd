@echo off
setlocal
cd /d "%~dp0"
title OpenPhysiologyLab Classroom
echo.
echo OpenPhysiologyLab Classroom - local teaching prototype
echo.
echo This starts a teacher dashboard on this laptop and allows student phones
echo on the same trusted Wi-Fi/LAN to join the classroom.
echo.
echo Do not use this prototype on an untrusted/public network.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0classroom_server.ps1"
if errorlevel 1 (
  echo.
  echo OPL Classroom could not start.
  pause
)
