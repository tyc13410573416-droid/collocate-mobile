# MCP Server 运行说明
$ErrorActionPreference = "Stop"
$python = (Get-Command python).Source
& $python (Join-Path $PSScriptRoot "server.py") --http 3001
