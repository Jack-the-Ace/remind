param(
  [ValidateSet('start','stop')] [string]$Action,
  [ValidateRange(1,65535)] [int]$ApiPort=8000,
  [ValidateRange(1,65535)] [int]$UiPort=5173
)
$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$runtime=Join-Path $root '.runtime'
$backend=Join-Path $root 'backend'
$frontend=Join-Path $root 'frontend'
$vite=Join-Path $frontend 'node_modules\vite\bin\vite.js'
$records=Join-Path $runtime 'services.json'
$services=@{}
$newRoles=@()
$lock=$null

function Save-State {
  $temp=Join-Path $runtime 'services.pending'
  [IO.File]::WriteAllText($temp,(ConvertTo-Json -InputObject $services))
  if ([IO.File]::Exists($records)) { [IO.File]::Replace($temp,$records,(Join-Path $runtime 'services.previous')) }
  else { [IO.File]::Move($temp,$records) }
}

function Get-Owned($role) {
  $r=$services[$role]
  if (!$r) { return }
  $proc=Get-Process -Id $r.pid -ErrorAction SilentlyContinue
  if (!$proc -or $proc.StartTime.ToUniversalTime().Ticks.ToString() -ne $r.started) { return }
  $info=Get-CimInstance Win32_Process -Filter ("ProcessId="+$r.pid)
  $marker=if ($role -eq 'backend') { '-m uvicorn app.main:app --app-dir "'+$backend+'"' } else { '"'+$vite+'"' }
  if (!$info -or $proc.Path -ne $r.exe -or !$info.CommandLine.Contains($marker)) {
    throw "Cannot verify ownership of $role PID $($r.pid). Process left running."
  }
  return $proc
}

function Stop-Owned($role) {
  $proc=Get-Owned $role
  if ($proc) {
    $proc.Kill()
    if (!$proc.WaitForExit(6000)) { throw "$role did not stop." }
    Write-Host "Stopped $role PID $($proc.Id)."
  }
  $services.Remove($role)
  Save-State
}

function Start-ServiceProcess($role,$exe,$arguments,$folder,$port) {
  $proc=Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $folder -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtime "$role.log") -RedirectStandardError (Join-Path $runtime "$role.error.log")
  $services[$role]=@{pid=$proc.Id;started=$proc.StartTime.ToUniversalTime().Ticks.ToString();exe=$exe;port=$port}
  $script:newRoles+=$role
  Save-State
}

function Wait-Ready($role,$url) {
  for ($i=0;$i -lt 40;$i++) {
    if (!(Get-Process -Id $services[$role].pid -ErrorAction SilentlyContinue)) { break }
    try {
      $res=Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 2
      if ($res.StatusCode -eq 200) { return $res }
    } catch { Start-Sleep -Milliseconds 250 }
  }
  throw "$role failed to serve $url. See $runtime\$role.error.log"
}

try {
  $null=[IO.Directory]::CreateDirectory($runtime)
  $lock=[IO.File]::Open((Join-Path $runtime 'launcher.lock'),'OpenOrCreate','ReadWrite','None')
  if (Test-Path -LiteralPath $records) {
    $state=Get-Content -LiteralPath $records -Raw | ConvertFrom-Json
    foreach ($prop in $state.PSObject.Properties) { $services[$prop.Name]=$prop.Value }
  }
  if ($Action -eq 'stop') {
    foreach ($role in @('frontend','backend')) { if ($services.ContainsKey($role)) { Stop-Owned $role } }
    Write-Host 'Project services stopped.'
    exit 0
  }
  if ($UiPort -eq $ApiPort) { throw 'Backend and frontend require different ports.' }
  $ports=@{backend=$ApiPort;frontend=$UiPort}
  foreach ($role in $ports.Keys) {
    if (Get-Owned $role) {
      if ($services[$role].port -ne $ports[$role]) { throw "Already running on port $($services[$role].port). Run stop.bat before changing ports." }
      Write-Host "Reusing $role PID $($services[$role].pid)."
    } else {
      $services.Remove($role)
      $tcp=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,$ports[$role])
      try { $tcp.ExclusiveAddressUse=$true; $tcp.Start() }
      catch { throw "Port $($ports[$role]) is unavailable. Choose other ports: start.bat 8014 5175" }
      finally { $tcp.Stop() }
    }
  }
  if (!$services.ContainsKey('backend')) {
    $venv=Join-Path $backend '.venv\Scripts\python.exe'
    if (!(Test-Path -LiteralPath $venv)) { throw 'Missing backend virtual environment. See README.md.' }
    # Start the actual interpreter directly so the recorded PID owns the listening socket.
    $base=(& $venv -c 'import sys; print(sys._base_executable)').Trim()
    $savedPath=$env:PYTHONPATH
    try {
      $env:PYTHONPATH=Join-Path $backend '.venv\Lib\site-packages'
      Start-ServiceProcess 'backend' $base ('-m uvicorn app.main:app --app-dir "'+$backend+'" --host 127.0.0.1 --port '+$ApiPort) $backend $ApiPort
    } finally { $env:PYTHONPATH=$savedPath }
  }
  $health=(Wait-Ready 'backend' "http://127.0.0.1:$ApiPort/api/health").Content | ConvertFrom-Json
  Write-Host "Demo ready. OpenAI key configured: $($health.llmConfigured)"
  if (!$services.ContainsKey('frontend')) {
    if (!(Test-Path -LiteralPath $vite)) { throw 'Missing Vite. Run npm ci in frontend.' }
    $env:PNJ_API_URL="http://127.0.0.1:$ApiPort"
    $node=(Get-Command node.exe).Source
    Push-Location -LiteralPath $frontend
    try {
      & $node $vite build *> (Join-Path $runtime 'frontend.build.log')
      if ($LASTEXITCODE -ne 0) { throw "Frontend build failed. See $runtime\frontend.build.log" }
    } finally { Pop-Location }
    # The browser opened by the batch file should retain its form across a
    # server restart. Serve the build without the dev client's automatic reload.
    Start-ServiceProcess 'frontend' $node ('"'+$vite+'" preview --host 127.0.0.1 --port '+$UiPort+' --strictPort') $frontend $UiPort
  }
  $url="http://127.0.0.1:$UiPort/"
  $survey=(Wait-Ready 'frontend' ($url+'api/survey')).Content | ConvertFrom-Json
  # Scoring is a read-only operation. Exercise the same POST through the same proxy as the browser.
  $sample=@{}
  foreach ($question in $survey.questions) { $sample[$question.id]=0 }
  if ($sample.Count -ne 20) { throw 'Unexpected survey definition from the frontend proxy.' }
  $body=@{version=$survey.version;answers=$sample} | ConvertTo-Json -Compress
  try {
    $score=Invoke-RestMethod -Method Post -Uri ($url+'api/survey/score') -ContentType 'application/json' -Body $body -TimeoutSec 5
    if (!$score.company -or !$score.plan) { throw 'Unexpected scoring response.' }
  } catch { throw "POST /api/survey/score failed via UI port $UiPort to API port $ApiPort. $($_.Exception.Message) See $runtime\backend.log and frontend.error.log." }
  Write-Host "App ready: $url"
  if (!$env:PNJ_NO_BROWSER) {
    try { Start-Process $url } catch { Write-Warning "Open $url in your browser. The servers are ready." }
  }
} catch {
  Write-Host "[ERROR] $($_.Exception.Message)"
  foreach ($role in $newRoles) { try { Stop-Owned $role } catch { Write-Host $_.Exception.Message } }
  exit 1
} finally { if ($lock) { $lock.Dispose() } }
