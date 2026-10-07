param(
    [int]$Port = 18765,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    throw '未找到 Python。请安装 Python 3.10+，并按 requirements-phase2.txt 安装离线依赖。'
}

Write-Host "能智核本地服务启动中：http://127.0.0.1:$Port"
Write-Host '本脚本不下载模型或调用付费 API；天气与设备档案使用仓库内缓存。'

if (-not $NoBrowser) {
    Start-Job -ScriptBlock {
        param($url)
        Start-Sleep -Milliseconds 800
        Start-Process $url
    } -ArgumentList "http://127.0.0.1:$Port/" | Out-Null
}

& $python.Source -X utf8 -m operation_planning.run_server --port $Port
