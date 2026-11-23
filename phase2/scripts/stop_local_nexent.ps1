$ErrorActionPreference = 'Stop'
# Stop only the distribution created for this project. Do not stop other WSLs.
& wsl.exe --terminate MedTraceNexent
if ($LASTEXITCODE -ne 0) { throw 'Could not stop the MedTraceNexent distribution.' }
Write-Host 'Stopped local Nexent, model and MedTrace services. Data is preserved.'
