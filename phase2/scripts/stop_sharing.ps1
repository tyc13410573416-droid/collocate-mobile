$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'sharing_common.ps1')
Set-Content -LiteralPath 'E:\MedTraceNexent\status\sharing.stop' -Value 'Stopped by user' -Encoding Ascii
$StatePath = 'E:\MedTraceNexent\status\sharing.json'
if (-not (Test-Path -LiteralPath $StatePath)) { Write-Host 'Sharing is not running.'; return }
$State = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
$ManagedPath = 'E:\MedTraceNexent\status\sharing-autostart.json'
if (Test-Path -LiteralPath $ManagedPath) {
    $Managed = Get-Content -LiteralPath $ManagedPath -Raw | ConvertFrom-Json
    if ($Managed.kind -eq 'scheduled-task') { Stop-ScheduledTask -TaskName $Managed.task_name -ErrorAction SilentlyContinue }
}
if (Test-OwnedMonitor $State) { Stop-Process -Id ([int]$State.monitor_pid) }
try { Publish-SharingAddress -Offline } catch { Write-Host 'Sharing stopped locally; the fixed page will detect the unavailable OCR service.' }
$TunnelProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $($State.pid)" -ErrorAction SilentlyContinue
if ($TunnelProcess -and $TunnelProcess.ExecutablePath -eq 'E:\MedTraceNexent\installers\cloudflared.exe' -and $TunnelProcess.CommandLine -match '127.0.0.1:5052') {
    Stop-Process -Id $TunnelProcess.ProcessId
    Write-Host 'Team sharing stopped. The local workspace remains available.'
} elseif ($TunnelProcess) { throw 'The saved process no longer matches this sharing service; nothing stopped.' }
else { Write-Host 'The sharing process has already exited.' }
