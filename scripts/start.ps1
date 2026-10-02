[CmdletBinding()]
param(
    [switch]$SkipModel,
    [ValidateRange(5, 60)][int]$ModelReadyTimeoutSeconds = 45
)

$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$runtimeDir = Join-Path $projectRoot 'runtime'
$pythonExe = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$serverScript = Join-Path $projectRoot 'server.py'
$modelExe = Join-Path $runtimeDir 'llama\llama-server.exe'
$workbenchRecord = Join-Path $runtimeDir 'workbench_process.json'

function Get-PortProcess([int]$Port) {
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    if ($listeners.Count -eq 0) { return $null }
    if (@($listeners | Where-Object { $_.LocalAddress -ne '127.0.0.1' }).Count -gt 0) {
        throw "Port $Port has a non-loopback listener. No existing process was changed."
    }
    $processIds = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    if ($processIds.Count -ne 1) { throw "Port $Port has ambiguous ownership. No process was changed." }
    $record = Get-CimInstance Win32_Process -Filter ('ProcessId = {0}' -f $processIds[0])
    if (-not $record) { throw "Could not verify the process on port $Port." }
    return $record
}

function Assert-ProjectProcess($Process, [string]$Kind) {
    $commandLine = [string]$Process.CommandLine
    if ($Kind -eq 'workbench') {
        $scriptPattern = '(?i)(?:^|\s)"?' + [regex]::Escape($serverScript) + '"?(?=\s|$)'
        if ($Process.ExecutablePath -ne $pythonExe -or $commandLine -notmatch $scriptPattern -or $commandLine -notmatch '--port\s+18190(?:\s|$)') {
            throw 'Port 18190 ownership is not provable from the bundled Python and absolute project server.py path. No process was changed. Stop the earlier launch from its original terminal, then use this script.'
        }
    } else {
        if ($Process.ExecutablePath -ne $modelExe -or $commandLine -notmatch '--port\s+18191(?:\s|$)' -or $commandLine -notmatch '--host\s+127\.0\.0\.1(?:\s|$)' -or $commandLine -notmatch '--alias\s+nengzhihe-qwen3-4b-q4km(?:\s|$)') {
            throw 'Port 18191 is not the verified project model process. No process was changed.'
        }
    }
}

function Read-LocalJson([string]$Url) {
    $request = [Net.HttpWebRequest]::Create($Url)
    $request.Proxy = $null
    $request.Timeout = 1500
    $response = $request.GetResponse()
    try {
        $reader = [IO.StreamReader]::new($response.GetResponseStream())
        try { return ($reader.ReadToEnd() | ConvertFrom-Json) }
        finally { $reader.Dispose() }
    } finally { $response.Dispose() }
}

function Wait-LocalReady([string]$Kind, [int]$TimeoutSeconds) {
    $timer = [Diagnostics.Stopwatch]::StartNew()
    do {
        try {
            if ($Kind -eq 'workbench') {
                $health = Read-LocalJson 'http://127.0.0.1:18190/api/health'
                if ($health.status -eq 'ok' -and $health.local_only -eq $true) { return $true }
            } else {
                $models = Read-LocalJson 'http://127.0.0.1:18191/v1/models'
                if (@($models.data | Where-Object { $_.id -eq 'nengzhihe-qwen3-4b-q4km' }).Count -gt 0) { return $true }
            }
        } catch { }
        Start-Sleep -Milliseconds 300
    } while ($timer.Elapsed.TotalSeconds -lt $TimeoutSeconds)
    return $false
}

foreach ($requiredFile in @($pythonExe, $serverScript)) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) { throw "Required file missing: $requiredFile" }
}

# Validate every occupied project port before launching anything. Never take over a port.
$workbenchProcess = Get-PortProcess 18190
if ($workbenchProcess) { Assert-ProjectProcess $workbenchProcess 'workbench' }
$modelProcess = $null
if (-not $SkipModel) {
    foreach ($requiredFile in @($modelExe, (Join-Path $runtimeDir 'Qwen3-4B-Q4_K_M.gguf'), (Join-Path $runtimeDir 'start_model.ps1'))) {
        if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) { throw "Model asset missing: $requiredFile. Prepare the verified model assets, or use -SkipModel for deterministic strategies." }
    }
    $modelProcess = Get-PortProcess 18191
    if ($modelProcess) { Assert-ProjectProcess $modelProcess 'model' }
}

New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
if (-not $workbenchProcess) {
    $arguments = '-X utf8 "' + $serverScript + '" --port 18190'
    $started = Start-Process -FilePath $pythonExe -ArgumentList $arguments -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDir 'workbench.stdout.log') -RedirectStandardError (Join-Path $runtimeDir 'workbench.stderr.log')
    $workbenchProcess = Get-CimInstance Win32_Process -Filter ('ProcessId = {0}' -f $started.Id)
    if (-not $workbenchProcess) { throw 'Workbench exited immediately. Read runtime/workbench.stderr.log.' }
    Assert-ProjectProcess $workbenchProcess 'workbench'
    Write-Output "Started workbench PID $($workbenchProcess.ProcessId) in a hidden window."
} else {
    Write-Output "Reusing verified workbench PID $($workbenchProcess.ProcessId)."
}

$record = [ordered]@{
    process_id = [int]$workbenchProcess.ProcessId
    executable = $pythonExe
    script = $serverScript
    port = 18190
    creation_utc = $workbenchProcess.CreationDate.ToUniversalTime().ToString('o')
    recorded_utc = [DateTime]::UtcNow.ToString('o')
}
$record | ConvertTo-Json | Set-Content -LiteralPath $workbenchRecord -Encoding utf8
if (-not (Wait-LocalReady 'workbench' 10)) { throw 'Workbench did not become ready. The PID record is preserved; inspect runtime/workbench.stderr.log.' }
Write-Output 'Workbench ready: http://127.0.0.1:18190'

if ($SkipModel) {
    Write-Output 'Model startup skipped. The workbench will report actual model availability.'
    return
}

if (-not $modelProcess) {
    & (Join-Path $runtimeDir 'start_model.ps1')
} else {
    # Only a fully verified project process can be adopted into the model PID record.
    [string]$modelProcess.ProcessId | Set-Content -LiteralPath (Join-Path $runtimeDir 'server.pid') -Encoding ascii
    Write-Output "Reusing verified model PID $($modelProcess.ProcessId)."
}
if (Wait-LocalReady 'model' $ModelReadyTimeoutSeconds) {
    $modelProcess = Get-PortProcess 18191
    Assert-ProjectProcess $modelProcess 'model'
    Write-Output 'Local model ready: http://127.0.0.1:18191/v1'
} else {
    Write-Warning 'Model readiness was not confirmed within the timeout. The workbench is available and will mark the model unavailable until its actual health check succeeds. Inspect runtime/server.stderr.log.'
}
