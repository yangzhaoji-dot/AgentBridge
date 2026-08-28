[CmdletBinding()]
param([switch]$NoPause)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot

try {
    & (Join-Path $projectRoot 'Stop-AgentBridgeConnector.ps1') -NoPause
    if ($LASTEXITCODE -ne 0) { throw 'Connector 停止失败。' }
    & (Join-Path $projectRoot 'Stop-AgentBridgeSshTunnel.ps1') -NoPause
    if ($LASTEXITCODE -ne 0) { throw 'SSH 隧道停止失败。' }
}
catch {
    Write-Host "停止失败：$($_.Exception.Message)" -ForegroundColor Red
    if (-not $NoPause) {
        Read-Host '按 Enter 关闭窗口'
    }
    exit 1
}
