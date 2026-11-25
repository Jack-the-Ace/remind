@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0share.ps1" stop
if errorlevel 1 (
  echo See .runtime\share for the project share logs.
  if not defined PNJ_NONINTERACTIVE pause
  exit /b 1
)
exit /b 0
