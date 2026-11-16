$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$logDir = Join-Path $PSScriptRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Test-Endpoint([string]$url) {
  try {
    Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2 | Out-Null
    return $true
  } catch {
    return $false
  }
}

if (-not (Test-Endpoint "http://127.0.0.1:5051/health")) {
  Start-Process -WindowStyle Hidden -FilePath python -ArgumentList "mock_nexent_api.py" `
    -WorkingDirectory $PSScriptRoot `
    -RedirectStandardOutput (Join-Path $logDir "mock.stdout.log") `
    -RedirectStandardError (Join-Path $logDir "mock.stderr.log") | Out-Null
  Start-Sleep -Milliseconds 800
}

if (-not (Test-Endpoint "http://127.0.0.1:5050/")) {
  $env:HOST = "0.0.0.0"
  $env:PORT = "5050"
  Start-Process -WindowStyle Hidden -FilePath python -ArgumentList "app.py" `
    -WorkingDirectory $PSScriptRoot `
    -RedirectStandardOutput (Join-Path $logDir "app.stdout.log") `
    -RedirectStandardError (Join-Path $logDir "app.stderr.log") | Out-Null
  Start-Sleep -Milliseconds 1000
}

$env:NPM_CONFIG_CACHE = Join-Path (Split-Path $PSScriptRoot -Parent) ".npm-cache"
Write-Host "前端已准备： http://127.0.0.1:5050"
Write-Host "正在创建临时公网链接，保持此窗口运行。"
npx --yes localtunnel --port 5050
