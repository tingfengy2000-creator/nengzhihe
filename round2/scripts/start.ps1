[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$roundRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$serverScript = Join-Path $roundRoot 'server.py'
$pythonExe = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$outputDirectory = Join-Path $roundRoot 'output'
$processRecord = Join-Path $outputDirectory 'workbench_process.json'

function Assert-RoundProcess($Process) {
    $pattern = '(?i)(?:^|\s)"?' + [regex]::Escape($serverScript) + '"?(?=\s|$)'
    if (-not $Process -or $Process.ExecutablePath -ne $pythonExe -or [string]$Process.CommandLine -notmatch $pattern -or [string]$Process.CommandLine -notmatch '--port\s+18192(?:\s|$)') {
        throw 'Port 18192 is not owned by this round2 server. No existing process was changed.'
    }
}
foreach ($file in @($serverScript,$pythonExe)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Required file missing: $file" }
}
New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
$listeners = @(Get-NetTCPConnection -State Listen -LocalPort 18192 -ErrorAction SilentlyContinue)
if (@($listeners | Where-Object { $_.LocalAddress -ne '127.0.0.1' }).Count -gt 0) { throw 'Port 18192 has a non-loopback listener. No process was changed.' }
$ownerIds = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
if ($ownerIds.Count -gt 1) { throw 'Port 18192 ownership is ambiguous. No process was changed.' }
if ($ownerIds.Count -eq 1) {
    $roundProcess = Get-CimInstance Win32_Process -Filter ('ProcessId = {0}' -f $ownerIds[0])
    Assert-RoundProcess $roundProcess
    Write-Output "Reusing round2 server PID $($roundProcess.ProcessId)."
} else {
    $arguments = '-X utf8 "' + $serverScript + '" --port 18192'
    $started = Start-Process -FilePath $pythonExe -ArgumentList $arguments -WorkingDirectory $roundRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $outputDirectory 'workbench.stdout.log') -RedirectStandardError (Join-Path $outputDirectory 'workbench.stderr.log')
    $roundProcess = Get-CimInstance Win32_Process -Filter ('ProcessId = {0}' -f $started.Id)
    Assert-RoundProcess $roundProcess
    Write-Output "Started round2 server PID $($roundProcess.ProcessId) in a hidden window."
}
[ordered]@{process_id=[int]$roundProcess.ProcessId;executable=$pythonExe;script=$serverScript;port=18192;creation_utc=$roundProcess.CreationDate.ToUniversalTime().ToString('o');recorded_utc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath $processRecord -Encoding utf8
$ready=$false
$timer=[Diagnostics.Stopwatch]::StartNew()
do {
    try {
        $request=[Net.HttpWebRequest]::Create('http://127.0.0.1:18192/api/health')
        $request.Proxy=$null
        $request.Timeout=1500
        $response=$request.GetResponse()
        try { $reader=[IO.StreamReader]::new($response.GetResponseStream());try { $health=$reader.ReadToEnd() | ConvertFrom-Json } finally {$reader.Dispose()} } finally {$response.Dispose()}
        if ($health.status -eq 'ok' -and $health.local_only -eq $true) {$ready=$true;break}
    } catch { }
    Start-Sleep -Milliseconds 300
} while ($timer.Elapsed.TotalSeconds -lt 10)
if (-not $ready) {throw 'Round2 server did not become ready. Inspect output/workbench.stderr.log. The process record is preserved.'}
Write-Output 'Round2 ready: http://127.0.0.1:18192'
Write-Output 'Only round2 port 18192 is managed. First-round workbench and model services are unchanged.'
