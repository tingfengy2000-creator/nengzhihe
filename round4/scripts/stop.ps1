[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$roundRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$serverScript = Join-Path $roundRoot 'server.py'
$pythonExe = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$processRecord = Join-Path $roundRoot 'output\workbench_process.json'
if (-not (Test-Path -LiteralPath $processRecord -PathType Leaf)) {Write-Output 'No round4 process record exists. No process was changed.';return}
$record=Get-Content -LiteralPath $processRecord -Raw | ConvertFrom-Json
$pythonExe=[string]$record.executable
if ($record.port -ne 18195 -or $record.script -ne $serverScript -or -not [IO.Path]::IsPathRooted($pythonExe)) {throw 'Round4 process record does not match this directory. No process was changed.'}
$roundProcess=Get-CimInstance Win32_Process -Filter ('ProcessId = {0}' -f [int]$record.process_id)
if (-not $roundProcess) {Write-Output 'Recorded round4 process is no longer running. No process was changed.';return}
$pattern='(?i)(?:^|\s)"?' + [regex]::Escape($serverScript) + '"?(?=\s|$)'
if ($record.creation_utc -is [DateTime]) {
    $recordCreationUtc = $record.creation_utc.ToUniversalTime()
} else {
    $recordCreationUtc = [DateTimeOffset]::Parse([string]$record.creation_utc, [Globalization.CultureInfo]::InvariantCulture).UtcDateTime
}
if ($roundProcess.ExecutablePath -ne $pythonExe -or [string]$roundProcess.CommandLine -notmatch $pattern -or [string]$roundProcess.CommandLine -notmatch '--port\s+18195(?:\s|$)' -or $roundProcess.CreationDate.ToUniversalTime().Ticks -ne $recordCreationUtc.Ticks) {throw 'The current process identity differs from the recorded round4 server. No process was changed.'}
Stop-Process -Id ([int]$roundProcess.ProcessId) -ErrorAction Stop
Write-Output "Stopped verified round4 server PID $($roundProcess.ProcessId). No first-round or other project service was changed."

