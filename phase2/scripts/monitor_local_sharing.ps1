$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'sharing_common.ps1')
$StopMarker = 'E:\MedTraceNexent\status\sharing.stop'
$LogPath = 'E:\MedTraceNexent\logs\sharing-recovery.log'

# A process-scoped power request prevents idle sleep only while sharing runs.
# It does not change the user's power plan or prevent an explicit shutdown.
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class MedTraceSharingPower {
    [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
    public struct Reason { public uint Version; public uint Flags; [MarshalAs(UnmanagedType.LPWStr)] public string Text; }
    [DllImport("kernel32.dll", SetLastError=true)] public static extern IntPtr PowerCreateRequest(ref Reason reason);
    [DllImport("kernel32.dll", SetLastError=true)] public static extern bool PowerSetRequest(IntPtr handle, int requestType);
    [DllImport("kernel32.dll", SetLastError=true)] public static extern bool PowerClearRequest(IntPtr handle, int requestType);
    [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr handle);
}
'@
$Reason = New-Object MedTraceSharingPower+Reason
$Reason.Version = 0
$Reason.Flags = 1
$Reason.Text = 'MedTrace team OCR sharing'
$PowerHandle = [MedTraceSharingPower]::PowerCreateRequest([ref]$Reason)
$PowerHeld = $PowerHandle -ne [IntPtr]::Zero -and $PowerHandle.ToInt64() -ne -1 -and [MedTraceSharingPower]::PowerSetRequest($PowerHandle, 1)
@{ monitor_pid = $PID; idle_sleep_inhibited = $PowerHeld } | ConvertTo-Json | Set-Content -LiteralPath 'E:\MedTraceNexent\status\sharing-monitor.json' -Encoding UTF8
$Failures = 0
$LastRestart = [DateTime]::MinValue
$LastPublicCheck = [DateTime]::MinValue
$RegistryPublished = $false
$PublicHealthy = $true
try {
    while (-not (Test-Path -LiteralPath $StopMarker)) {
        try {
            $State = Read-SharingState
            $LocalReady = $false
            try { $LocalReady = (Invoke-RestMethod -Uri 'http://127.0.0.1:5052/api/image-status' -TimeoutSec 4).configured } catch { }
            if (-not $LocalReady) { & (Join-Path $PSScriptRoot 'start_local_nexent.ps1') -NoBrowser }
            $Healthy = Test-OwnedTunnel $State
            if ($Healthy -and ((Get-Date) - $LastPublicCheck).TotalSeconds -ge 60) {
                $LastPublicCheck = Get-Date
                try { $PublicHealthy = (Invoke-RestMethod -Uri ($State.url + '/api/image-status') -TimeoutSec 8).configured } catch { $PublicHealthy = $false }
            }
            $Healthy = $Healthy -and $PublicHealthy
            if ($Healthy) {
                $Failures = 0
                if (-not $RegistryPublished) { Publish-SharingAddress; $RegistryPublished = $true }
            } else { $Failures++ }
            if ($Failures -ge 3 -and ((Get-Date) - $LastRestart).TotalSeconds -ge 180) {
                $LastRestart = Get-Date
                if (Test-OwnedTunnel $State) { Stop-Process -Id ([int]$State.pid) }
                & (Join-Path $PSScriptRoot 'share_local_nexent.ps1') -NoBrowser -SkipMonitor
                $State = Read-SharingState
                $State | Add-Member -NotePropertyName monitor_pid -NotePropertyValue $PID -Force
                Write-SharingState $State
                $Failures = 0
                $RegistryPublished = $true
                $PublicHealthy = $true
                Add-Content -LiteralPath $LogPath -Value "$(Get-Date -Format o) Team connection recovered."
            }
        } catch {
            $RegistryPublished = $false
            Add-Content -LiteralPath $LogPath -Value "$(Get-Date -Format o) Recovery pending; will retry."
        }
        Start-Sleep -Seconds 15
    }
} finally {
    if ($PowerHeld) { [MedTraceSharingPower]::PowerClearRequest($PowerHandle, 1) | Out-Null }
    if ($PowerHandle -ne [IntPtr]::Zero -and $PowerHandle.ToInt64() -ne -1) { [MedTraceSharingPower]::CloseHandle($PowerHandle) | Out-Null }
}
