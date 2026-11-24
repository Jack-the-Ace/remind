@echo off
setlocal EnableExtensions
set "PROJECT_ROOT=%~dp0"
set "RUNTIME_DIR=%PROJECT_ROOT%.runtime"

echo.
echo [PnJ Avatar AI] Stopping only this project's services...
call :stop_service "%RUNTIME_DIR%\backend.pid" "uvicorn" "backend"
call :stop_service "%RUNTIME_DIR%\frontend.pid" "vite" "frontend"
echo [OK] Stop operation finished.
exit /b 0

:stop_service
if not exist "%~1" (
  echo [INFO] %~3 is not recorded as running.
  exit /b 0
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$pidFile='%~1'; $marker='%~2'; $folder='%~3'; try{$id=[int](Get-Content -LiteralPath $pidFile -ErrorAction Stop)}catch{Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue; exit 2}; $p=Get-CimInstance Win32_Process -Filter ('ProcessId='+$id) -ErrorAction SilentlyContinue; $rootTag=[IO.Path]::GetFileName($env:PROJECT_ROOT.TrimEnd('\')); if($p -and $p.CommandLine -like ('*'+$rootTag+'*') -and $p.CommandLine -like ('*'+$marker+'*') -and $p.CommandLine -like ('*'+$folder+'*')) { Stop-Process -Id $id -Force; Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue; exit 0 }; Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue; exit 1"
if errorlevel 2 echo [WARNING] %~3 PID file was invalid and has been cleared.
if errorlevel 1 if not errorlevel 2 echo [INFO] %~3 was not running, or did not belong to this project. Nothing was stopped.
if not errorlevel 1 echo [OK] Stopped this project's %~3 service.
exit /b 0
