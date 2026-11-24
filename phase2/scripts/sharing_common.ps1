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
    $RuntimeConfig = 'E:\MedTraceNexent\status\sharing-autostart.json'
    $PythonExecutable = $null
    if (Test-Path -LiteralPath $RuntimeConfig) { $PythonExecutable = (Get-Content -LiteralPath $RuntimeConfig -Raw | ConvertFrom-Json).python }
    if (-not $PythonExecutable) { $PythonExecutable = (Get-Command python -ErrorAction Stop).Source }
    & $PythonExecutable @Arguments
    if ($LASTEXITCODE -ne 0) { throw 'Could not update the fixed team entry.' }
}

function Start-SharingMonitor {
    $State = Read-SharingState
    if (Test-OwnedMonitor $State) { return }
    $ManagedConfigPath = 'E:\MedTraceNexent\status\sharing-autostart.json'
    if (Test-Path -LiteralPath $ManagedConfigPath) {
        $Managed = Get-Content -LiteralPath $ManagedConfigPath -Raw | ConvertFrom-Json
        if ($Managed.kind -eq 'scheduled-task') {
            $Task = Get-ScheduledTask -TaskName $Managed.task_name -ErrorAction Stop
            if ($Task.State -ne 'Running') { Start-ScheduledTask -TaskName $Managed.task_name }
            return
        }
    }
    # WMI launches the user-owned process outside the invoking terminal's job.
    $Command = '"' + (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') + '" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "E:\MedTraceNexent\scripts\monitor_local_sharing.ps1"'
    $Created = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $Command; CurrentDirectory = 'E:\MedTraceNexent' }
    if ($Created.ReturnValue -ne 0) { throw 'Could not launch the independent sharing monitor.' }
    $State | Add-Member -NotePropertyName monitor_pid -NotePropertyValue ([int]$Created.ProcessId) -Force
    Write-SharingState $State
}
