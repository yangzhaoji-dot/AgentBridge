[CmdletBinding()]
param(
    [string]$Version
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$versionPath = Join-Path $projectRoot 'VERSION'
if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = (Get-Content -LiteralPath $versionPath -Raw).Trim()
}
$distRoot = Join-Path $projectRoot 'dist'
$releaseName = "AgentBridge-v$Version"
$stagePath = Join-Path $distRoot $releaseName
$archivePath = Join-Path $distRoot "$releaseName-win-edge.zip"
$hashPath = "$archivePath.sha256"

if ([string]::IsNullOrWhiteSpace($Version)) {
    throw 'VERSION 文件为空。'
}
if ((Test-Path -LiteralPath $stagePath) -or (Test-Path -LiteralPath $archivePath)) {
    throw "发布目录或 ZIP 已存在：$releaseName。请修改版本号后重新构建。"
}

New-Item -ItemType Directory -Path $stagePath -Force | Out-Null

$items = @(
    '.codex',
    'agentbridge_connector',
    'agentbridge_server',
    'deploy',
    'extension',
    'scripts',
    'tests',
    '.env.example',
    '.gitattributes',
    '.gitignore',
    'AGENTS.md',
    'CONTRIBUTING.md',
    'Create-AgentBridgeShortcuts.ps1',
    'EDGE_MVP.md',
    'Install-AgentBridge.ps1',
    'LICENSE',
    'package-lock.json',
    'package.json',
    'README.md',
    'requirements.txt',
    'SECURITY.md',
    'SSH_TUNNEL_DEPLOYMENT.md',
    'Start-AgentBridge.ps1',
    'Start-AgentBridgeConnector.ps1',
    'Start-AgentBridgeSshConnector.ps1',
    'Start-AgentBridgeSshTunnel.ps1',
    'Stop-AgentBridgeConnector.ps1',
    'Stop-AgentBridgeSshConnector.ps1',
    'Stop-AgentBridgeSshTunnel.ps1',
    'Stop-AgentBridge.ps1',
    'SERVER_DEPLOYMENT.md',
    'VERSION'
)

foreach ($item in $items) {
    $source = Join-Path $projectRoot $item
    if (-not (Test-Path -LiteralPath $source)) {
        throw "发布文件缺失：$item"
    }
    Copy-Item -LiteralPath $source -Destination $stagePath -Recurse -Force -Exclude '__pycache__', '.pytest_cache', '*.pyc'
}

$stageFullPath = [IO.Path]::GetFullPath($stagePath)
$generatedDirectories = Get-ChildItem -LiteralPath $stagePath -Recurse -Directory -Force | Where-Object {
    $_.Name -in @('__pycache__', '.pytest_cache')
}
foreach ($directory in $generatedDirectories) {
    $directoryFullPath = [IO.Path]::GetFullPath($directory.FullName)
    if (-not $directoryFullPath.StartsWith($stageFullPath, [StringComparison]::OrdinalIgnoreCase)) {
        throw "拒绝清理发布暂存目录外的路径：$directoryFullPath"
    }
    Remove-Item -LiteralPath $directoryFullPath -Recurse -Force
}

Get-ChildItem -LiteralPath $stagePath -Recurse -File -Filter '*.pyc' | ForEach-Object {
    Remove-Item -LiteralPath $_.FullName -Force
}

Compress-Archive -LiteralPath $stagePath -DestinationPath $archivePath -CompressionLevel Optimal
$hash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLower()
Set-Content -LiteralPath $hashPath -Value "$hash *$(Split-Path -Leaf $archivePath)" -NoNewline

Write-Host "已构建：$archivePath" -ForegroundColor Green
Write-Host "SHA256：$hash"
