[CmdletBinding()]
param([switch]$NoPause)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot

try {
    & (Join-Path $projectRoot 'Stop-AgentBridgeConnector.ps1') -NoPause
    & (Join-Path $projectRoot 'Stop-AgentBridgeSshTunnel.ps1') -NoPause
}
catch {
    Write-Host "停止失败：$($_.Exception.Message)" -ForegroundColor Red
    if (-not $NoPause) {
        Read-Host '按 Enter 关闭窗口'
    }
    exit 1
}
