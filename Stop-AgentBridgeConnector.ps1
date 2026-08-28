[CmdletBinding()]
param([switch]$NoPause)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pidPath = Join-Path $projectRoot '.runtime\agentbridge-connector.pid'

try {
    if (-not (Test-Path -LiteralPath $pidPath)) {
        Write-Host 'AgentBridge Connector 没有运行。'
        return
    }

    $savedPid = [int](Get-Content -LiteralPath $pidPath -Raw).Trim()
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $savedPid" -ErrorAction SilentlyContinue
    if ($process) {
        if ($process.CommandLine -notlike "*$projectRoot*" -or $process.CommandLine -notlike '*agentbridge_connector*') {
            throw "PID $savedPid 现在属于其他程序，已拒绝停止。"
        }
        Stop-Process -Id $savedPid -Force
        Write-Host 'AgentBridge Connector 已停止。' -ForegroundColor Green
    }
    else {
        Write-Host 'AgentBridge Connector 已经退出。'
    }
    Remove-Item -LiteralPath $pidPath -Force
}
catch {
    Write-Host "停止失败：$($_.Exception.Message)" -ForegroundColor Red
    if (-not $NoPause) {
        Read-Host '按 Enter 关闭窗口'
    }
    exit 1
}
