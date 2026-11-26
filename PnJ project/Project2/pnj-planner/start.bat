@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0services.ps1" start
set "planner_rc=%errorlevel%"
if not "%planner_rc%"=="0" if not defined PNJ_PLANNER_UNATTENDED pause
exit /b %planner_rc%
