$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'sharing_common.ps1')
$Root = 'E:\MedTraceNexent'
$ConfigPath = Join-Path $Root 'status\sharing-autostart.json'
$TaskName = 'MedTrace-Team-OCR'
$MonitorPath = Join-Path $Root 'scripts\monitor_local_sharing.ps1'
$ShellPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
if (-not (Test-Path -LiteralPath $MonitorPath)) { throw 'Install the monitor script before registering startup.' }
$PythonPath = (Get-Command python -ErrorAction Stop).Source
$StopMarker = Join-Path $Root 'status\sharing.stop'
if (Test-Path -LiteralPath $StopMarker) { Remove-Item -LiteralPath $StopMarker }
$Managed = @{ python = $PythonPath; monitor = $MonitorPath; kind = 'startup-shortcut' }
try {
    $Scheduler = New-Object -ComObject 'Schedule.Service'
    $Scheduler.Connect()
    $Folder = $Scheduler.GetFolder('\')
    $ExistingTask = $null
    try { $ExistingTask = $Folder.GetTask($TaskName) } catch { }
    if ($ExistingTask -and $ExistingTask.Definition.Actions.Item(1).Arguments -notmatch 'MedTraceNexent.+monitor_local_sharing.ps1') {
        throw 'An unrelated task uses the requested name; nothing replaced.'
    }
    $Definition = $Scheduler.NewTask(0)
    $Definition.RegistrationInfo.Description = 'MedTrace team OCR sharing: user logon startup and independent recovery.'
    $UserSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $Definition.Principal.UserId = $UserSid
    $Definition.Principal.LogonType = 3
    $Definition.Principal.RunLevel = 0
    $Definition.Settings.ExecutionTimeLimit = 'PT0S'
    $Definition.Settings.MultipleInstances = 2
    $Definition.Settings.StartWhenAvailable = $true
    $Definition.Settings.DisallowStartIfOnBatteries = $false
    $Definition.Settings.StopIfGoingOnBatteries = $false
    $Definition.Settings.RestartCount = 10
    $Definition.Settings.RestartInterval = 'PT1M'
    $Trigger = $Definition.Triggers.Create(9)
    $Trigger.UserId = $UserSid
    $Trigger.Delay = 'PT30S'
    $RetryTrigger = $Definition.Triggers.Create(1)
    $RetryTrigger.StartBoundary = [DateTime]::Now.AddMinutes(1).ToString('s')
    $RetryTrigger.Repetition.Interval = 'PT5M'
    $RetryTrigger.Enabled = $true
    $Action = $Definition.Actions.Create(0)
    $Action.Path = $ShellPath
    $Action.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $MonitorPath + '"'
    $Action.WorkingDirectory = $Root
    $Registered = $Folder.RegisterTaskDefinition($TaskName, $Definition, 6, $UserSid, $null, 3, $null)
    $Managed.kind = 'scheduled-task'
    $Managed.task_name = $TaskName
} catch {
    # User Startup is a no-admin fallback, still launched by Windows at logon.
    $Startup = [Environment]::GetFolderPath('Startup')
    $ShortcutPath = Join-Path $Startup 'MedTrace OCR Sharing.lnk'
    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $ShellPath
    $Shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $MonitorPath + '"'
    $Shortcut.WorkingDirectory = $Root
    $Shortcut.WindowStyle = 7
    $Shortcut.Description = 'MedTrace OCR sharing startup'
    $Shortcut.Save()
    $Managed.shortcut = $ShortcutPath
}
$Managed | ConvertTo-Json | Set-Content -LiteralPath $ConfigPath -Encoding UTF8
Start-SharingMonitor
Write-Host ('Windows-managed sharing enabled: ' + $Managed.kind)
