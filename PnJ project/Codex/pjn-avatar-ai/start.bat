@echo off
setlocal EnableExtensions
set "PROJECT_ROOT=%~dp0"
set "RUNTIME_DIR=%PROJECT_ROOT%.runtime"
set "BACKEND_PYTHON=%PROJECT_ROOT%backend\.venv\Scripts\python.exe"
set "VITE_ENTRY=%PROJECT_ROOT%frontend\node_modules\vite\bin\vite.js"
set "BACKEND_PORT=8000"
set "FRONTEND_PORT=5173"
if not "%~1"=="" set "BACKEND_PORT=%~1"
if not "%~2"=="" set "FRONTEND_PORT=%~2"

echo.
echo [PnJ Avatar AI] Starting local services...

if not exist "%BACKEND_PYTHON%" (
  echo [ERROR] Python virtual environment is missing: backend\.venv
  echo         Run the backend setup steps in README.md first.
  exit /b 1
)
if not exist "%VITE_ENTRY%" (
  echo [ERROR] Frontend packages are missing: frontend\node_modules
  echo         Run: cd frontend ^&^& npm install
  exit /b 1
)
where node.exe >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Node.js was not found in PATH. Install Node.js, then try again.
  exit /b 1
)

if not exist "%RUNTIME_DIR%" mkdir "%RUNTIME_DIR%"

call :check_existing "%RUNTIME_DIR%\backend.pid" "uvicorn" "backend"
if not errorlevel 1 (
  echo [INFO] This project's backend is already running.
  set "BACKEND_RUNNING=1"
)
call :check_existing "%RUNTIME_DIR%\frontend.pid" "vite" "frontend"
if not errorlevel 1 (
  echo [INFO] This project's frontend is already running.
  set "FRONTEND_RUNNING=1"
)

if defined BACKEND_RUNNING if defined FRONTEND_RUNNING (
  echo [INFO] Opening the existing app at http://127.0.0.1:%FRONTEND_PORT%/
  start "" "http://127.0.0.1:%FRONTEND_PORT%/"
  exit /b 0
)

call :port_available %BACKEND_PORT%
if errorlevel 1 if not defined BACKEND_RUNNING (
  echo [ERROR] Port %BACKEND_PORT% is already in use by another process.
  echo         The launcher will not stop a process it did not start.
  exit /b 1
)
call :port_available %FRONTEND_PORT%
if errorlevel 1 if not defined FRONTEND_RUNNING (
  echo [ERROR] Port %FRONTEND_PORT% is already in use by another process.
  echo         The launcher will not stop a process it did not start.
  exit /b 1
)

call :check_api_key

if not defined BACKEND_RUNNING (
  echo [INFO] Starting FastAPI on port %BACKEND_PORT%...
  powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$root=$env:PROJECT_ROOT; $runtime=Join-Path $root '.runtime'; $p=Start-Process -FilePath (Join-Path $root 'backend\.venv\Scripts\python.exe') -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','%BACKEND_PORT%') -WorkingDirectory (Join-Path $root 'backend') -RedirectStandardOutput (Join-Path $runtime 'backend.log') -RedirectStandardError (Join-Path $runtime 'backend.error.log') -WindowStyle Hidden -PassThru; $p.Id | Set-Content -LiteralPath (Join-Path $runtime 'backend.pid')"
  if errorlevel 1 goto :start_error
)
if not defined FRONTEND_RUNNING (
  echo [INFO] Starting Vite on port %FRONTEND_PORT%...
  set "VITE_API_URL=http://127.0.0.1:%BACKEND_PORT%"
  powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$root=$env:PROJECT_ROOT; $runtime=Join-Path $root '.runtime'; $node=(Get-Command node.exe -ErrorAction Stop).Source; $entry=Join-Path $root 'frontend\node_modules\vite\bin\vite.js'; $args=[char]34+$entry+[char]34+' --host 127.0.0.1 --port %FRONTEND_PORT% --strictPort'; $p=Start-Process -FilePath $node -ArgumentList $args -WorkingDirectory (Join-Path $root 'frontend') -RedirectStandardOutput (Join-Path $runtime 'frontend.log') -RedirectStandardError (Join-Path $runtime 'frontend.error.log') -WindowStyle Hidden -PassThru; $p.Id | Set-Content -LiteralPath (Join-Path $runtime 'frontend.pid')"
  if errorlevel 1 goto :start_error
)

call :wait_for_port %BACKEND_PORT% 15
if errorlevel 1 (
  echo [ERROR] Backend did not become ready. See .runtime\backend.error.log
  type "%RUNTIME_DIR%\backend.error.log" 2>nul
  call "%PROJECT_ROOT%stop.bat" >nul 2>nul
  exit /b 1
)
call :wait_for_port %FRONTEND_PORT% 15
if errorlevel 1 (
  echo [ERROR] Frontend did not become ready. See .runtime\frontend.error.log
  type "%RUNTIME_DIR%\frontend.error.log" 2>nul
  call "%PROJECT_ROOT%stop.bat" >nul 2>nul
  exit /b 1
)

echo [OK] Backend:  http://127.0.0.1:%BACKEND_PORT%/api/health
echo [OK] Frontend: http://127.0.0.1:%FRONTEND_PORT%/
start "" "http://127.0.0.1:%FRONTEND_PORT%/"
exit /b 0

:check_api_key
if not exist "%PROJECT_ROOT%backend\.env" (
  echo [WARNING] backend\.env was not found. AI recommendation requests will return a clear configuration error.
  echo           Copy backend\.env.example to backend\.env and set OPENAI_API_KEY.
  exit /b 0
)
set "OPENAI_KEY_VALUE="
for /f "tokens=1,* delims==" %%A in ('findstr /R /C:"^[ ]*OPENAI_API_KEY[ ]*=" "%PROJECT_ROOT%backend\.env"') do set "OPENAI_KEY_VALUE=%%B"
if not defined OPENAI_KEY_VALUE (
  echo [WARNING] OPENAI_API_KEY is missing or empty in backend\.env.
  exit /b 0
)
echo [OK] OPENAI_API_KEY is configured. Its value is not displayed.
exit /b 0

:check_existing
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$pidFile='%~1'; $marker='%~2'; $folder='%~3'; if(!(Test-Path -LiteralPath $pidFile)){exit 1}; try{$id=[int](Get-Content -LiteralPath $pidFile -ErrorAction Stop)}catch{Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue; exit 1}; $p=Get-CimInstance Win32_Process -Filter ('ProcessId='+$id) -ErrorAction SilentlyContinue; $rootTag=[IO.Path]::GetFileName($env:PROJECT_ROOT.TrimEnd('\')); if($p -and $p.CommandLine -like ('*'+$rootTag+'*') -and $p.CommandLine -like ('*'+$marker+'*') -and $p.CommandLine -like ('*'+$folder+'*')){exit 0}; Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue; exit 1"
exit /b %errorlevel%

:port_available
powershell.exe -NoProfile -Command "$listener=New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback,%~1); try{$listener.Start(); $listener.Stop(); exit 0}catch{exit 1}"
exit /b %errorlevel%

:wait_for_port
powershell.exe -NoProfile -Command "$until=(Get-Date).AddSeconds(%~2); do { $client=New-Object Net.Sockets.TcpClient; try { $client.Connect('127.0.0.1',%~1); $client.Close(); exit 0 } catch { Start-Sleep -Milliseconds 400 } finally { $client.Dispose() } } while((Get-Date)-lt $until); exit 1"
exit /b %errorlevel%

:start_error
echo [ERROR] A service process could not be started. Check .runtime\backend.error.log and .runtime\frontend.error.log.
call "%PROJECT_ROOT%stop.bat" >nul 2>nul
exit /b 1
