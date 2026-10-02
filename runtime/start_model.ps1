$ErrorActionPreference = 'Stop'
$runtimeDir = $PSScriptRoot
$exe = Join-Path $runtimeDir 'llama\llama-server.exe'
$model = Join-Path $runtimeDir 'Qwen3-4B-Q4_K_M.gguf'
if (-not (Test-Path -LiteralPath $exe)) { throw "Runner missing: $exe" }
if (-not (Test-Path -LiteralPath $model)) { throw "Model missing: $model" }
$listener = Get-NetTCPConnection -State Listen -LocalPort 18191 -ErrorAction SilentlyContinue
if ($listener) {
    Write-Output 'Port 18191 already has a listener. No process was changed. Check /health and /v1/models.'
    exit 0
}
$arguments = @('-m', '..\Qwen3-4B-Q4_K_M.gguf', '--alias', 'nengzhihe-qwen3-4b-q4km', '--host', '127.0.0.1', '--port', '18191', '-c', '4096', '-np', '1', '-t', '4', '-tb', '4', '-ngl', 'all', '-b', '256', '-ub', '128', '--jinja', '--reasoning-budget', '0', '--prio', '-1', '--poll', '0', '--no-webui')
$process = Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory (Split-Path $exe) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDir 'server.stdout.log') -RedirectStandardError (Join-Path $runtimeDir 'server.stderr.log')
$process.Id | Set-Content -LiteralPath (Join-Path $runtimeDir 'server.pid') -Encoding ascii
Write-Output "Started this project's local model process: $($process.Id). Endpoint http://127.0.0.1:18191"
