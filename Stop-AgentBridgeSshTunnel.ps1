[CmdletBinding()]
param([switch]$NoPause)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$runtimeDir = Join-Path $projectRoot '.runtime'
$pidPath = Join-Path $runtimeDir 'agentbridge-ssh-tunnel.pid'
$metadataPath = Join-Path $runtimeDir 'agentbridge-ssh-tunnel.json'

try {
    if (-not (Test-Path -LiteralPath $pidPath) -or -not (Test-Path -LiteralPath $metadataPath)) {
        Write-Host 'AgentBridge SSH 隧道没有运行。'
        return
    }

    $metadata = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
    $savedPid = [int](Get-Content -LiteralPath $pidPath -Raw).Trim()
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $savedPid" -ErrorAction SilentlyContinue
    $forward = '127.0.0.1:{0}:127.0.0.1:{1}' -f $metadata.LocalPort, $metadata.RemotePort
    if ($process) {
        if ($process.CommandLine -notlike "*$forward*" -or $process.CommandLine -notlike "*$($metadata.SshHost)*") {
            throw "PID $savedPid 现在不是记录的 AgentBridge SSH 隧道，已拒绝停止。"
        }
        Stop-Process -Id $savedPid -Force
        Write-Host 'AgentBridge SSH 隧道已停止。' -ForegroundColor Green
    }
    else {
        Write-Host 'AgentBridge SSH 隧道已经退出。'
    }
    Remove-Item -LiteralPath $pidPath -Force
    Remove-Item -LiteralPath $metadataPath -Force
}
catch {
    Write-Host "停止失败：$($_.Exception.Message)" -ForegroundColor Red
    if (-not $NoPause) {
        Read-Host '按 Enter 关闭窗口'
    }
    exit 1
}
