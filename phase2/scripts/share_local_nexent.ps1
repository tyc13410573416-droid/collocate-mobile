param([switch]$NoBrowser, [switch]$SkipMonitor)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'sharing_common.ps1')
$DeploymentRoot = 'E:\MedTraceNexent'
$StatePath = Join-Path $DeploymentRoot 'status\sharing.json'
$TeamUrl = 'https://tyc13410573416-droid.github.io/collocate-mobile/'
$TunnelTool = Join-Path $DeploymentRoot 'installers\cloudflared.exe'
$StopMarker = Join-Path $DeploymentRoot 'status\sharing.stop'
if (-not $SkipMonitor -and (Test-Path -LiteralPath $StopMarker)) { Remove-Item -LiteralPath $StopMarker }
& (Join-Path $PSScriptRoot 'start_local_nexent.ps1') -NoBrowser
if (-not (Test-Path -LiteralPath $TunnelTool)) { throw 'The official cloudflared binary is missing from the installation directory.' }
if (Test-Path -LiteralPath $StatePath) {
    $Previous = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
    $Existing = Get-CimInstance Win32_Process -Filter "ProcessId = $($Previous.pid)" -ErrorAction SilentlyContinue
    if ($Existing -and $Existing.ExecutablePath -eq $TunnelTool -and $Existing.CommandLine -match '127.0.0.1:5052') {
        $TeamUrl | Set-Content -LiteralPath (Join-Path $DeploymentRoot 'team-url.txt') -Encoding UTF8
        Publish-SharingAddress
        if (-not $SkipMonitor) { Start-SharingMonitor }
        Write-Host 'Fixed team URL: https://tyc13410573416-droid.github.io/collocate-mobile/'
        if (-not $NoBrowser) { Start-Process 'https://tyc13410573416-droid.github.io/collocate-mobile/' }
        return
    }
}
$RunStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$OutputLog = Join-Path $DeploymentRoot "logs\sharing-$RunStamp.stdout.log"
$ErrorLog = Join-Path $DeploymentRoot "logs\sharing-$RunStamp.stderr.log"
$TunnelProcess = Start-Process -FilePath $TunnelTool -ArgumentList @('tunnel', '--no-autoupdate', '--url', 'http://127.0.0.1:5052', '--protocol', 'http2') -WindowStyle Hidden -PassThru -RedirectStandardOutput $OutputLog -RedirectStandardError $ErrorLog
$PriorMonitor = (Read-SharingState).monitor_pid
@{ pid = $TunnelProcess.Id; url = ''; executable = $TunnelTool; log = $ErrorLog; monitor_pid = $PriorMonitor } | ConvertTo-Json | Set-Content -LiteralPath $StatePath -Encoding UTF8
$PublicUrl = ''
for ($Attempt = 0; $Attempt -lt 60; $Attempt++) {
    if (Test-Path -LiteralPath $StopMarker) { Stop-Process -Id $TunnelProcess.Id -ErrorAction SilentlyContinue; throw 'Sharing was stopped.' }
    $TunnelProcess.Refresh()
    if ($TunnelProcess.HasExited) { throw "Sharing tool exited. See $ErrorLog" }
    $LogText = ''
    foreach ($LogPath in @($OutputLog, $ErrorLog)) {
        if (Test-Path -LiteralPath $LogPath) {
            $LogStream = $null
            $LogReader = $null
            try {
                $LogStream = [System.IO.File]::Open($LogPath, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
                $LogReader = [System.IO.StreamReader]::new($LogStream)
                $LogText += $LogReader.ReadToEnd()
            } catch [System.IO.IOException] { }
            finally {
                if ($LogReader) { $LogReader.Dispose() }
                elseif ($LogStream) { $LogStream.Dispose() }
            }
        }
    }
    $Match = [regex]::Match($LogText, 'https://[a-z0-9-]+\.trycloudflare\.com')
    if ($Match.Success) { $PublicUrl = $Match.Value; break }
    Start-Sleep -Seconds 1
}
if (-not $PublicUrl) {
    Stop-Process -Id $TunnelProcess.Id -ErrorAction SilentlyContinue
    throw "No public URL returned yet. See $ErrorLog"
}
@{ pid = $TunnelProcess.Id; url = $PublicUrl; executable = $TunnelTool; log = $ErrorLog; monitor_pid = $PriorMonitor } | ConvertTo-Json | Set-Content -LiteralPath $StatePath -Encoding UTF8
& wsl.exe -d MedTraceNexent -u root -- python3 /mnt/e/MedTraceNexent/scripts/configure_sharing_origin.py
if ($LASTEXITCODE -ne 0) { throw 'Could not configure the verified team URL.' }
& wsl.exe -d MedTraceNexent -u root -- systemctl restart medtrace-api
if ($LASTEXITCODE -ne 0) { throw 'Could not reload the image backend.' }
$TeamUrl | Set-Content -LiteralPath (Join-Path $DeploymentRoot 'team-url.txt') -Encoding UTF8
Publish-SharingAddress
if (-not $SkipMonitor) { Start-SharingMonitor }
Write-Host 'Fixed team URL: https://tyc13410573416-droid.github.io/collocate-mobile/'
Write-Host 'Free local OCR sharing with recovery. Shutdown still makes live OCR unavailable.'
if (-not $NoBrowser) { Start-Process 'https://tyc13410573416-droid.github.io/collocate-mobile/' }
