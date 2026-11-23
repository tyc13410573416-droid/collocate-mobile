param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$DeploymentRoot = 'E:\MedTraceNexent'
$StatePath = Join-Path $DeploymentRoot 'status\sharing.json'
$TunnelTool = Join-Path $DeploymentRoot 'installers\cloudflared.exe'
& (Join-Path $PSScriptRoot 'start_local_nexent.ps1') -NoBrowser
if (-not (Test-Path -LiteralPath $TunnelTool)) { throw 'The official cloudflared binary is missing from the installation directory.' }
if (Test-Path -LiteralPath $StatePath) {
    $Previous = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
    $Existing = Get-CimInstance Win32_Process -Filter "ProcessId = $($Previous.pid)" -ErrorAction SilentlyContinue
    if ($Existing -and $Existing.ExecutablePath -eq $TunnelTool -and $Existing.CommandLine -match '127.0.0.1:5052') {
        Write-Host "Team URL: $($Previous.url)"
        if (-not $NoBrowser) { Start-Process $Previous.url }
        return
    }
}
$RunStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$OutputLog = Join-Path $DeploymentRoot "logs\sharing-$RunStamp.stdout.log"
$ErrorLog = Join-Path $DeploymentRoot "logs\sharing-$RunStamp.stderr.log"
$TunnelProcess = Start-Process -FilePath $TunnelTool -ArgumentList @('tunnel', '--no-autoupdate', '--url', 'http://127.0.0.1:5052', '--protocol', 'http2') -WindowStyle Hidden -PassThru -RedirectStandardOutput $OutputLog -RedirectStandardError $ErrorLog
$PublicUrl = ''
for ($Attempt = 0; $Attempt -lt 60; $Attempt++) {
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
@{ pid = $TunnelProcess.Id; url = $PublicUrl; executable = $TunnelTool; log = $ErrorLog } | ConvertTo-Json | Set-Content -LiteralPath $StatePath -Encoding UTF8
& wsl.exe -d MedTraceNexent -u root -- python3 /mnt/e/MedTraceNexent/scripts/configure_sharing_origin.py
if ($LASTEXITCODE -ne 0) { throw 'Could not configure the verified team URL.' }
& wsl.exe -d MedTraceNexent -u root -- systemctl restart medtrace-api
if ($LASTEXITCODE -ne 0) { throw 'Could not reload the image backend.' }
$PublicUrl | Set-Content -LiteralPath (Join-Path $DeploymentRoot 'team-url.txt') -Encoding UTF8
Write-Host "Team URL: $PublicUrl"
Write-Host 'Free temporary HTTPS sharing. Keep this computer awake. Restarting sharing may change the URL.'
if (-not $NoBrowser) { Start-Process $PublicUrl }
