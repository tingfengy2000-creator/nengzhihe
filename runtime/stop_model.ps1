$ErrorActionPreference = 'Stop'
$pidFile = Join-Path $PSScriptRoot 'server.pid'
if (-not (Test-Path -LiteralPath $pidFile)) { Write-Output 'No project model PID file.'; exit 0 }
$modelProcessId = [int](Get-Content -LiteralPath $pidFile -Raw).Trim()
$expectedExe = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'llama\llama-server.exe'))
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$modelProcessId"
if (-not $process) { Write-Output 'This project model process has already exited.'; exit 0 }
if ($process.ExecutablePath -ne $expectedExe -or $process.CommandLine -notmatch '--port\s+18191(?:\s|$)') {
    throw 'PID identity differs from this project model. No process was stopped.'
}
Stop-Process -Id $modelProcessId
Write-Output "Stopped only this project model PID $modelProcessId."
