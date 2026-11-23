<## Install only the two small native analyze_image prompts in a running container. #>
[CmdletBinding()]
param(
    [string]$Container = 'nexent-runtime',
    [switch]$SkipRestart
)
$ErrorActionPreference = 'Stop'
if ($Container -notmatch '^[a-zA-Z0-9][a-zA-Z0-9_.-]*$') { throw '容器名称格式不正确。' }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw '未找到 Docker。请在运行 Nexent 的电脑上执行本脚本。'
}
$promptRoot = Join-Path $PSScriptRoot 'prompts'
foreach ($lang in @('zh', 'en')) {
    if (-not (Test-Path -LiteralPath (Join-Path $promptRoot "$lang/analyze_image.yaml"))) {
        throw "接入包不完整：缺少 $lang 提示词。"
    }
}
# Discover the installed SDK location instead of assuming a container directory.
$probe = "import json,pathlib,nexent; p=pathlib.Path(nexent.__file__).resolve().parent/'core'/'prompts'; print(json.dumps({x:str(p/x/'tool'/'analyze_image.yaml') for x in ('zh','en')}))"
$probeOutput = & docker exec $Container python -c $probe
if ($LASTEXITCODE -ne 0) { throw '无法读取 Nexent SDK 路径，请确认容器名称与主服务状态。' }
$paths = ($probeOutput -join "`n") | ConvertFrom-Json
$backupDir = Join-Path $PSScriptRoot ("backups/" + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
$copied = @()
try {
    # Back up both files before the first replacement.
    foreach ($lang in @('zh', 'en')) {
        $target = [string]$paths.$lang
        if (-not $target.StartsWith('/') -or -not $target.EndsWith("/core/prompts/$lang/tool/analyze_image.yaml")) {
            throw 'SDK 返回的提示词路径不符合预期，未进行修改。'
        }
        & docker cp "${Container}:$target" (Join-Path $backupDir "$lang.yaml")
        if ($LASTEXITCODE -ne 0) { throw "无法备份 $lang 提示词。" }
    }
    foreach ($lang in @('zh', 'en')) {
        & docker cp (Join-Path $promptRoot "$lang/analyze_image.yaml") "${Container}:$($paths.$lang)"
        if ($LASTEXITCODE -ne 0) { throw "复制 $lang 提示词失败。" }
        $copied += $lang
    }
    if (-not $SkipRestart) {
        & docker restart $Container
        if ($LASTEXITCODE -ne 0) { throw '容器重启失败，请查看 Nexent 日志。' }
    }
} catch {
    foreach ($lang in $copied) {
        & docker cp (Join-Path $backupDir "$lang.yaml") "${Container}:$($paths.$lang)" | Out-Null
    }
    throw
}
Write-Host '已安装完整转录提示词，没有重建或下载 data-process 镜像。'
Write-Host "备份位置：$backupDir"
Write-Host '接下来在 Nexent 配置图片理解模型、启用 Agent 的 analyze_image，并测试真实图片。'
Write-Host '注意：容器重建后这些文件可能恢复，需要重跑本脚本或按说明设置持久挂载。'
