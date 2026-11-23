function Read-SharingState {
    $Path = 'E:\MedTraceNexent\status\sharing.json'
    if (Test-Path -LiteralPath $Path) { return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json }
    return $null
}

function Write-SharingState($State) {
    $State | ConvertTo-Json | Set-Content -LiteralPath 'E:\MedTraceNexent\status\sharing.json' -Encoding UTF8
}

function Test-OwnedTunnel($State) {
    if (-not $State) { return $false }
    $ProcessInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$State.pid)" -ErrorAction SilentlyContinue
    return [bool]($ProcessInfo -and $ProcessInfo.ExecutablePath -eq 'E:\MedTraceNexent\installers\cloudflared.exe' -and $ProcessInfo.CommandLine -match '127.0.0.1:5052')
}

function Test-OwnedMonitor($State) {
    if (-not $State -or -not $State.monitor_pid) { return $false }
    $ProcessInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$State.monitor_pid)" -ErrorAction SilentlyContinue
    return [bool]($ProcessInfo -and $ProcessInfo.Name -eq 'powershell.exe' -and $ProcessInfo.CommandLine -match 'MedTraceNexent.+monitor_local_sharing.ps1')
}

function Publish-SharingAddress([switch]$Offline) {
    $Arguments = @('E:\MedTraceNexent\scripts\publish_shared_backend.py')
    if ($Offline) { $Arguments += '--offline' }
    & python @Arguments
    if ($LASTEXITCODE -ne 0) { throw 'Could not update the fixed team entry.' }
}

function Start-SharingMonitor {
    $State = Read-SharingState
    if (Test-OwnedMonitor $State) { return }
    $ProcessInfo = Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'E:\MedTraceNexent\scripts\monitor_local_sharing.ps1') -WindowStyle Hidden -PassThru -RedirectStandardOutput 'E:\MedTraceNexent\logs\sharing-monitor.stdout.log' -RedirectStandardError 'E:\MedTraceNexent\logs\sharing-monitor.stderr.log'
    $State | Add-Member -NotePropertyName monitor_pid -NotePropertyValue $ProcessInfo.Id -Force
    Write-SharingState $State
}
