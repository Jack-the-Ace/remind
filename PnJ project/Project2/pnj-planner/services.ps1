param([Parameter(Mandatory=$true)][ValidateSet('start','stop')] [string]$Action)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$runtime = Join-Path $root '.runtime'
$record = Join-Path $runtime 'server.json'
$serverScript = Join-Path $root 'backend\serve.py'
$venv = Join-Path $root '.venv\Scripts\python.exe'
$port = 5186
$url = "http://127.0.0.1:$port/"
$lock = $null
$launched = $null

function Get-PlannerProcess {
    if (!(Test-Path -LiteralPath $record)) { return }
    $state = Get-Content -LiteralPath $record -Raw | ConvertFrom-Json
    $proc = Get-Process -Id $state.pid -ErrorAction SilentlyContinue
    if (!$proc) { return }
    # Keep the process handle open during verification and termination.
    $null = $proc.Handle
    if ($proc.StartTime.ToUniversalTime().Ticks.ToString() -ne $state.started) { return }
    $info = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $state.pid)
    if ($proc.Path -ne $state.exe -or !$info -or !$info.CommandLine.Contains('"' + $serverScript + '"')) {
        throw "Cannot confirm ownership of PID $($state.pid). Check $record."
    }
    return $proc
}

function Open-Planner {
    Write-Host "PnJ Seoul Planner is ready at $url"
    Write-Host "Logs: $runtime"
    if (!$env:PNJ_PLANNER_NO_BROWSER) { Start-Process $url }
}

function Get-DatabasePath {
    if (!$env:PNJ_PLANNER_DB) { return Join-Path $runtime 'planner.sqlite3' }
    if ([IO.Path]::IsPathRooted($env:PNJ_PLANNER_DB)) { $path = [IO.Path]::GetFullPath($env:PNJ_PLANNER_DB) }
    else { $path = [IO.Path]::GetFullPath((Join-Path $root $env:PNJ_PLANNER_DB)) }
    if (!$path.StartsWith($runtime+'\',[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Choose a planner database under this project .runtime directory.'
    }
    return $path
}

try {
    $null = [IO.Directory]::CreateDirectory($runtime)
    $lock = [IO.File]::Open((Join-Path $runtime 'launcher.lock'),'OpenOrCreate','ReadWrite','None')
    $owned = Get-PlannerProcess
    if ($Action -eq 'stop') {
        if ($owned) {
            $owned.Kill()
            if (!$owned.WaitForExit(6000)) { throw "Planner PID $($owned.Id) did not stop." }
        }
        if (Test-Path -LiteralPath $record) { Remove-Item -LiteralPath $record }
        Write-Host 'PnJ Seoul Planner stopped.'
        exit 0
    }
    $database = Get-DatabasePath
    if ($owned) {
        $state = Get-Content -LiteralPath $record -Raw | ConvertFrom-Json
        if ($state.database -ne $database) { throw 'The running planner uses a different database. Run this planner stop.bat before switching.' }
        $health = Invoke-RestMethod ($url + 'api/health') -TimeoutSec 4
        if ($health.service -ne 'pnj-planner') { throw "Unexpected service at $url" }
        Open-Planner
        exit 0
    }
    $probe = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $port)
    try { $probe.ExclusiveAddressUse=$true; $probe.Start() }
    catch { throw "Port $port is occupied. Close the program using this port to start PnJ Seoul Planner." }
    finally { $probe.Stop() }

    if (!(Test-Path -LiteralPath $venv)) { throw 'Install the new Python environment as described in README.md.' }
    $frontend = Join-Path $root 'frontend'
    $vite = Join-Path $frontend 'node_modules\vite\bin\vite.js'
    if (!(Test-Path -LiteralPath $vite)) { throw 'Run npm ci in the new frontend folder (see README.md).' }
    $env:PNJ_PLANNER_DB=$database
    $node = (Get-Command node.exe).Source
    Push-Location -LiteralPath $frontend
    try {
        $build = Start-Process -FilePath $node -ArgumentList ('"'+$vite+'" build') -WorkingDirectory $frontend -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput (Join-Path $runtime 'build.log') -RedirectStandardError (Join-Path $runtime 'build.error.log')
        if ($build.ExitCode -ne 0) { throw "Vite build failed ($($build.ExitCode)). See build.error.log." }
    } finally { Pop-Location }
    $base = (& $venv -I -c 'import sys; print(sys._base_executable)').Trim()
    $launched = Start-Process -FilePath $base -ArgumentList ('-I -S "'+$serverScript+'" '+$port) -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtime 'server.log') -RedirectStandardError (Join-Path $runtime 'server.error.log')
    $identity = @{pid=$launched.Id; started=$launched.StartTime.ToUniversalTime().Ticks.ToString(); exe=$base; database=$database}
    [IO.File]::WriteAllText($record, ($identity | ConvertTo-Json))
    $ready = $false
    for ($i=0; $i -lt 45; $i++) {
        if ($launched.HasExited) { break }
        try {
            $health = Invoke-RestMethod ($url+'api/health') -TimeoutSec 2
            $survey = Invoke-RestMethod ($url+'api/survey') -TimeoutSec 2
            $ui = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 2
            if ($health.service -eq 'pnj-planner' -and $survey.items.Count -gt 0 -and $survey.version -and $ui.StatusCode -eq 200) { $ready=$true; break }
        } catch { Start-Sleep -Milliseconds 250 }
    }
    if (!$ready) {
        Get-Content -LiteralPath (Join-Path $runtime 'server.error.log') -Tail 12
        throw 'Planner startup check failed. See server.error.log.'
    }
    Open-Planner
} catch {
    if ($launched -and !$launched.HasExited) { $launched.Kill(); $null=$launched.WaitForExit(5000) }
    $problem=$_.Exception.Message
    Write-Host ("ERROR: "+$problem)
    try { Add-Content -LiteralPath (Join-Path $runtime 'launcher.error.log') -Value ((Get-Date -Format o)+' '+$Action+' '+$problem) } catch {}
    Write-Host "Logs and installation instructions: $runtime and $root\README.md"
    exit 1
} finally {
    if ($lock) { $lock.Dispose() }
}
