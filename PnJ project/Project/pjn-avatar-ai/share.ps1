param([ValidateSet('start','stop')][string]$Action = 'start')
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$dir = Join-Path $root '.runtime\share'
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'
$port = 18743
$origin = "http://127.0.0.1:$port"
$stateFile = Join-Path $dir 'processes.json'
$linkFile = Join-Path $dir 'url.txt'
$config = Join-Path $dir 'quick.yml'
$services = @{}
$created = @()
$lock = $null

function Save-Processes {
    $pending = Join-Path $dir 'processes.pending'
    [IO.File]::WriteAllText($pending, (ConvertTo-Json -InputObject $services))
    if ([IO.File]::Exists($stateFile)) { [IO.File]::Replace($pending,$stateFile,(Join-Path $dir 'processes.previous')) }
    else { [IO.File]::Move($pending,$stateFile) }
}
function Get-Owned($role) {
    $record = $services[$role]
    if (!$record) { return }
    $process = Get-Process -Id $record.pid -ErrorAction SilentlyContinue
    if (!$process -or $process.StartTime.ToUniversalTime().Ticks.ToString() -ne $record.started) { return }
    $info = Get-CimInstance Win32_Process -Filter ("ProcessId="+$process.Id)
    $marker = if ($role -eq 'origin') { 'app.share:app --app-dir "'+$backend+'"' } else { '--config "'+$config+'"' }
    if (!$info -or $process.Path -ne $record.exe -or !$info.CommandLine.Contains($marker)) {
        throw "Cannot confirm ownership of $role PID $($process.Id). Left it running."
    }
    return $process
}
function Stop-Owned($role) {
    $process = Get-Owned $role
    if ($process) {
        $process.Kill()
        if (!$process.WaitForExit(6000)) { throw "Could not stop share $role." }
        Write-Host "Stopped share $role PID $($process.Id)."
    }
    $services.Remove($role)
    Save-Processes
}
function Start-Owned($role,$exe,$arguments,$folder,$instance) {
    $process = Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $folder -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $dir "$role.log") -RedirectStandardError (Join-Path $dir "$role.error.log")
    try {
        $services[$role] = @{pid=$process.Id; exe=$exe; started=$process.StartTime.ToUniversalTime().Ticks.ToString(); instance=$instance}
        Save-Processes
        $script:created += $role
    } catch {
        if (!$process.HasExited) { $process.Kill() }
        throw
    }
}
function Get-Connector {
    $installed = Get-Command cloudflared.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($installed) { return $installed.Source }
    $exe = Join-Path $dir 'cloudflared.exe'
    if (Test-Path -LiteralPath $exe) { return $exe }
    if ($env:PROCESSOR_ARCHITECTURE -ne 'AMD64') { throw 'Install cloudflared for this Windows architecture from developers.cloudflare.com/tunnel/downloads/.' }
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $release = Invoke-RestMethod 'https://api.github.com/repos/cloudflare/cloudflared/releases/latest'
    $asset = $release.assets | Where-Object name -eq 'cloudflared-windows-amd64.exe'
    if ($asset.digest -notmatch '^sha256:([a-fA-F0-9]{64})$') { throw 'Official cloudflared release digest unavailable.' }
    $expected = $Matches[1]
    $temp = Join-Path $dir 'cloudflared.download'
    Invoke-WebRequest -UseBasicParsing -Uri $asset.browser_download_url -OutFile $temp
    if ((Get-FileHash -LiteralPath $temp).Hash -ne $expected) { throw 'cloudflared download checksum mismatch.' }
    Move-Item -LiteralPath $temp -Destination $exe -Force
    return $exe
}
function Wait-Health($url,$instance,$attempts,$role) {
    $failure = 'No response'
    for ($i=0; $i -lt $attempts; $i++) {
        if (!(Get-Owned $role)) { throw "$role exited. See $dir\$role.error.log" }
        try {
            $health = Invoke-RestMethod -Uri ($url+'/api/health') -TimeoutSec 5
            if ($health.mode -eq 'shared-demo' -and $health.instance -eq $instance -and $health.llmConfigured -eq $false) { return }
            $failure = 'Unexpected origin or mode'
        } catch { $failure = $_.Exception.Message }
        Start-Sleep -Milliseconds 750
    }
    throw "Shared health check failed at $url ($failure). Check DNS, connectivity and $dir\$role.error.log"
}

try {
    $null = [IO.Directory]::CreateDirectory($dir)
    $lock = [IO.File]::Open((Join-Path $dir 'launcher.lock'),'OpenOrCreate','ReadWrite','None')
    if (Test-Path -LiteralPath $stateFile) {
        $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
        foreach ($prop in $state.PSObject.Properties) { $services[$prop.Name]=$prop.Value }
    }
    if ($Action -eq 'stop') {
        foreach ($role in @('tunnel','origin')) { if ($services.ContainsKey($role)) { Stop-Owned $role } }
        [IO.File]::Delete($linkFile)
        Write-Host 'Sharing stopped. The demo database is retained.'
        exit 0
    }
    if (!(Get-Owned 'origin')) {
        if (Get-Owned 'tunnel') { Stop-Owned 'tunnel' }
        [IO.File]::Delete($linkFile)
        $socket = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,$port)
        try { $socket.ExclusiveAddressUse=$true; $socket.Start() }
        catch { throw "Share port $port is occupied. Close the conflicting service or change the share port in share.ps1." }
        finally { $socket.Stop() }
        $venv = Join-Path $backend '.venv\Scripts\python.exe'
        $vite = Join-Path $frontend 'node_modules\vite\bin\vite.js'
        if (!(Test-Path $venv) -or !(Test-Path $vite)) { throw 'Install project dependencies as described in README.md.' }
        $base = (& $venv -c 'import sys; print(sys._base_executable)').Trim()
        $site = Join-Path $dir 'site'
        Push-Location $frontend
        try {
            & node.exe $vite build --mode share --outDir $site --emptyOutDir *> (Join-Path $dir 'build.log')
            if ($LASTEXITCODE -ne 0) { throw "Share UI build failed. See $dir\build.log" }
        } finally { Pop-Location }
        $env:PNJ_SHARE_DEMO='1'
        $env:OPENAI_API_KEY=$null
        $env:PYTHON_DOTENV_DISABLED='1'
        $env:PYTHONPATH=Join-Path $backend '.venv\Lib\site-packages'
        $env:PNJ_SHARE_INSTANCE=[Guid]::NewGuid().ToString('N')
        Start-Owned 'origin' $base ('-m uvicorn app.share:app --app-dir "'+$backend+'" --host 127.0.0.1 --port '+$port+' --no-access-log') $backend $env:PNJ_SHARE_INSTANCE
    }
    $instance = $services.origin.instance
    Wait-Health $origin $instance 12 'origin'
    $survey = Invoke-RestMethod ($origin+'/api/survey') -TimeoutSec 5
    if ($survey.questions.Count -ne 20 -or (Invoke-WebRequest -UseBasicParsing $origin -TimeoutSec 5).Content -notmatch 'id="root"') { throw 'Share UI or survey is unavailable.' }
    if (!(Get-Owned 'tunnel')) {
        [IO.File]::Delete($linkFile)
        $connector = Get-Connector
        # Ignore unrelated named-tunnel settings on the host. Only forward to the shared origin.
        [IO.File]::WriteAllText($config,"{}")
        Start-Owned 'tunnel' $connector ('tunnel --config "'+$config+'" --no-autoupdate --protocol http2 --http-host-header 127.0.0.1 --url '+$origin) $dir $instance
    }
    $log = Join-Path $dir 'tunnel.error.log'
    $url=$null
    for ($i=0; $i -lt 60; $i++) {
        if (!(Get-Owned 'tunnel')) { throw "cloudflared exited. Check $log and outbound Cloudflare connectivity." }
        $content = Get-Content -LiteralPath $log -Raw -ErrorAction SilentlyContinue
        if ($content -match '(https://[a-z0-9-]+\.trycloudflare\.com)\s') { $url = $Matches[1]; break }
        Start-Sleep -Milliseconds 500
    }
    if (!$url) { throw "No Quick Tunnel URL received. Check $log and access to api.trycloudflare.com." }
    Wait-Health $url $instance 32 'tunnel'
    [IO.File]::WriteAllText($linkFile,$url)
    Write-Host "`nTEAM DEMO (HTTPS): $url`n" -ForegroundColor Green
    try { Set-Clipboard -Value $url -ErrorAction Stop } catch { Write-Host "Copy the link above or open $linkFile." }
    if (!$env:PNJ_NO_BROWSER) { try { Start-Process $url } catch { Write-Warning "Open $url in your browser." } }
    Write-Host 'Keep this PC awake and connected. Close this window freely; share_stop.bat ends sharing.'
} catch {
    Write-Host "[ERROR] $($_.Exception.Message)"
    foreach ($role in @('tunnel','origin')) { if ($created -contains $role) { try { Stop-Owned $role } catch { Write-Warning $_ } } }
    exit 1
} finally { if ($lock) { $lock.Dispose() } }
