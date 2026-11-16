param(
  [switch]$SkipDataBuild
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not $SkipDataBuild) {
  python scripts/generate_demo_data.py
  python scripts/clean_medical_data.py
  python scripts/generate_charts.py
}

Write-Host "Starting Mock Nexent on http://127.0.0.1:5051"
Start-Process -WindowStyle Hidden -FilePath python -ArgumentList "mock_nexent_api.py"
Write-Host "Starting frontend on http://127.0.0.1:5050"
python app.py
