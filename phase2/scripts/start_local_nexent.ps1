param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$Distro = 'MedTraceNexent'
$DeploymentRoot = 'E:\MedTraceNexent'
$Keepalive = Get-CimInstance Win32_Process -Filter "Name = 'wsl.exe'" | Where-Object {
    $_.CommandLine -match 'MedTraceNexent' -and $_.CommandLine -match 'sleep infinity'
}
if (-not $Keepalive) {
    $Process = Start-Process -FilePath 'wsl.exe' -ArgumentList @('-d', $Distro, '-u', 'root', '--', 'sleep', 'infinity') -WindowStyle Hidden -PassThru
    @{ pid = $Process.Id; distro = $Distro } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $DeploymentRoot 'status\wsl-keepalive.json') -Encoding UTF8
}
& wsl.exe -d $Distro -u root -- systemctl start docker medtrace-local-llm medtrace-mcp medtrace-api
if ($LASTEXITCODE -ne 0) { throw 'Local services failed to start.' }
Write-Host 'Starting local Nexent and MedTrace. Please wait...'
$Ready = $false
for ($Attempt = 0; $Attempt -lt 90; $Attempt++) {
    try {
        $Platform = Invoke-WebRequest -Uri 'http://127.0.0.1:3000/' -UseBasicParsing -TimeoutSec 3
        $Api = Invoke-RestMethod -Uri 'http://127.0.0.1:5052/api/image-status' -TimeoutSec 3
        # Windows port 8080 is used by Codex Bridge on this PC. Check the model
        # inside its WSL network, without changing that existing Windows service.
        $ModelJson = & wsl.exe -d $Distro -u root -- curl -fsS --max-time 3 http://127.0.0.1:8080/health 2>$null
        $Model = $ModelJson | ConvertFrom-Json
        if ($Platform.StatusCode -eq 200 -and $Api.configured -and $Model.status -eq 'ok') { $Ready = $true; break }
    } catch { }
    Start-Sleep -Seconds 2
}
if (-not $Ready) { throw 'Startup health checks did not pass. Keep this window output for troubleshooting.' }
Write-Host 'MedTrace: http://127.0.0.1:5052'
Write-Host 'Nexent:   http://127.0.0.1:3000'
if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:5052' }
