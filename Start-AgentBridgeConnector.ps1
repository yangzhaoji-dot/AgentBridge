[CmdletBinding()]
param([switch]$NoPause)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$runtimeDir = Join-Path $projectRoot '.runtime'
$logDir = Join-Path $runtimeDir 'logs'
$pidPath = Join-Path $runtimeDir 'agentbridge-connector.pid'
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$healthUrl = 'http://127.0.0.1:8765/api/health'
$statusUrl = 'http://127.0.0.1:8765/api/status'

function Test-ConnectorHealth {
    try {
        return (Invoke-RestMethod -Uri $healthUrl -TimeoutSec 1).status -eq 'ok'
    }
    catch {
        return $false
    }
}

try {
    if ([string]::IsNullOrWhiteSpace($env:AGENTBRIDGE_REMOTE_WS_URL)) {
        throw '请先设置 AGENTBRIDGE_REMOTE_WS_URL，例如 wss://bridge.example.com/ws/connector。'
    }
    if ([string]::IsNullOrWhiteSpace($env:AGENTBRIDGE_PAIRING_TOKEN)) {
        throw '请先设置 AGENTBRIDGE_PAIRING_TOKEN。不要把它写入 Git 或聊天记录。'
    }
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        throw "找不到 Python 虚拟环境：$pythonPath"
    }
    if (Test-ConnectorHealth) {
        throw '8765 端口已有服务。请先停止本机 AgentBridge，再启动 Connector 模式。'
    }
    if (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) {
        throw '8765 端口已被其他程序占用。'
    }

    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    $process = Start-Process -FilePath $pythonPath `
        -ArgumentList @('-m', 'agentbridge_connector') `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDir 'agentbridge-connector.out.log') `
        -RedirectStandardError (Join-Path $logDir 'agentbridge-connector.err.log') `
        -PassThru
    [IO.File]::WriteAllText($pidPath, [string]$process.Id)

    for ($attempt = 0; $attempt -lt 80; $attempt++) {
        if (Test-ConnectorHealth) { break }
        Start-Sleep -Milliseconds 250
    }
    if (-not (Test-ConnectorHealth)) {
        throw 'Connector 没有按时启动。请检查 .runtime\logs\agentbridge-connector.err.log。'
    }

    $status = Invoke-RestMethod -Uri $statusUrl -TimeoutSec 2
    Write-Host 'AgentBridge Connector 已启动。' -ForegroundColor Green
    Write-Host "设备 ID：$($status.device_id)" -ForegroundColor Cyan
    Write-Host "远程 Relay 已连接：$($status.remote_connected)" -ForegroundColor Cyan
    Write-Host "Edge 扩展已连接：$($status.extension_online)" -ForegroundColor Cyan
}
catch {
    Write-Host "启动失败：$($_.Exception.Message)" -ForegroundColor Red
    if (-not $NoPause) {
        Read-Host '按 Enter 关闭窗口'
    }
    exit 1
}
