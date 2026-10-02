[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
param([switch]$KeepModel)

$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$runtimeDir = Join-Path $projectRoot 'runtime'
$pythonExe = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$serverScript = Join-Path $projectRoot 'server.py'
$modelExe = Join-Path $runtimeDir 'llama\llama-server.exe'
$workbenchRecord = Join-Path $runtimeDir 'workbench_process.json'
$modelPidFile = Join-Path $runtimeDir 'server.pid'

function Get-RecordedProcess([int]$ProcessId, [string]$Kind, [datetime]$CreationUtc = [datetime]::MinValue) {
    $process = Get-CimInstance Win32_Process -Filter ('ProcessId = {0}' -f $ProcessId)
    if (-not $process) { return $null }
    $commandLine = [string]$process.CommandLine
    if ($Kind -eq 'workbench') {
        $scriptPattern = '(?i)(?:^|\s)"?' + [regex]::Escape($serverScript) + '"?(?=\s|$)'
        if ($process.ExecutablePath -ne $pythonExe -or $commandLine -notmatch $scriptPattern -or $commandLine -notmatch '--port\s+18190(?:\s|$)') {
            throw "PID $ProcessId is not provably this workbench. No process was stopped."
        }
        if ($CreationUtc -ne [datetime]::MinValue -and $process.CreationDate.ToUniversalTime().Ticks -ne $CreationUtc.ToUniversalTime().Ticks) {
            throw "PID $ProcessId has been reused since the workbench record was written. No process was stopped."
        }
    } else {
        if ($process.ExecutablePath -ne $modelExe -or $commandLine -notmatch '--port\s+18191(?:\s|$)' -or $commandLine -notmatch '--host\s+127\.0\.0\.1(?:\s|$)' -or $commandLine -notmatch '--alias\s+nengzhihe-qwen3-4b-q4km(?:\s|$)') {
            throw "PID $ProcessId is not provably this project's local model. No process was stopped."
        }
    }
    return $process
}

# First validate all identities. Never terminate by image name or port alone.
$plans = @()
if (Test-Path -LiteralPath $workbenchRecord -PathType Leaf) {
    $record = Get-Content -LiteralPath $workbenchRecord -Raw | ConvertFrom-Json
    if ($record.executable -ne $pythonExe -or $record.script -ne $serverScript -or $record.port -ne 18190) {
        throw 'Workbench PID record does not match this project. No process was stopped.'
    }
    if (-not $record.creation_utc) { throw 'Workbench PID record has no creation timestamp. No process was stopped.' }
    $recordedCreation = ([datetime]$record.creation_utc).ToUniversalTime()
    $process = Get-RecordedProcess ([int]$record.process_id) 'workbench' $recordedCreation
    if ($process) {
        $plans += [pscustomobject]@{ Kind = 'workbench'; Id = [int]$record.process_id; CreationUtc = $recordedCreation; RecordPath = $workbenchRecord }
    } else { Write-Output 'Recorded workbench process has already exited.' }
} else {
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort 18190 -ErrorAction SilentlyContinue)
    if ($listeners.Count -gt 0) {
        throw 'Port 18190 is active but no project workbench PID record exists. No process was stopped. Use the original launching terminal, or start.ps1 after the earlier launch exits.'
    }
    Write-Output 'No workbench PID record or active project port.'
}

if (-not $KeepModel) {
    if (Test-Path -LiteralPath $modelPidFile -PathType Leaf) {
        $modelProcessId = [int](Get-Content -LiteralPath $modelPidFile -Raw).Trim()
        $process = Get-RecordedProcess $modelProcessId 'model'
        if ($process) {
            $plans += [pscustomobject]@{ Kind = 'model'; Id = $modelProcessId; CreationUtc = $process.CreationDate.ToUniversalTime(); RecordPath = $modelPidFile }
        } else { Write-Output 'Recorded model process has already exited.' }
    } else { Write-Output 'No project model PID record; no model process will be stopped.' }
}

foreach ($plan in $plans) {
    if ($PSCmdlet.ShouldProcess("$($plan.Kind) PID $($plan.Id)", 'Stop only the verified project process')) {
        $process = Get-RecordedProcess $plan.Id $plan.Kind $plan.CreationUtc
        if ($process) {
            if ($process.CreationDate.ToUniversalTime().Ticks -ne $plan.CreationUtc.ToUniversalTime().Ticks) { throw 'Process identity changed during verification; stop aborted.' }
            Stop-Process -Id $plan.Id
            Remove-Item -LiteralPath $plan.RecordPath -Force
            Write-Output "Stopped verified $($plan.Kind) PID $($plan.Id)."
        }
    }
}
