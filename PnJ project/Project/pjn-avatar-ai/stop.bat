@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0services.ps1" stop
if errorlevel 1 (
  echo Check the message above and the .runtime logs.
  if not defined PNJ_NONINTERACTIVE pause
  exit /b 1
)
