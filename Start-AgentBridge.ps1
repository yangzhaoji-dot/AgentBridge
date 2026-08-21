[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$NoPause
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$runtimeDir = Join-Path $projectRoot '.runtime'
$logDir = Join-Path $runtimeDir 'logs'
$pidPath = Join-Path $runtimeDir 'agentbridge.pid'
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$healthUrl = 'http://127.0.0.1:8765/api/health'
$statusUrl = 'http://127.0.0.1:8765/api/status'

function Test-AgentBridgeHealth {
    try {
        return (Invoke-RestMethod -Uri $healthUrl -TimeoutSec 1).status -eq 'ok'
    }
    catch {
        return $false
    }
}

function Test-OwnedPid {
    if (-not (Test-Path -LiteralPath $pidPath)) {
        return $false
    }
    $savedPid = [int](Get-Content -LiteralPath $pidPath -Raw).Trim()
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $savedPid" -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        return $false
    }
    return $process.CommandLine -like "*$projectRoot*" -and $process.CommandLine -like '*agentbridge_server.app*'
}

function Wait-ForHealth {
    for ($attempt = 0; $attempt -lt 80; $attempt++) {
        if (Test-AgentBridgeHealth) {
            return $true
        }
        Start-Sleep -Milliseconds 250
    }
    return $false
}

try {
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        throw "找不到 Python 虚拟环境：$pythonPath"
    }
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null

    if (Test-AgentBridgeHealth) {
        if (-not (Test-OwnedPid)) {
            throw '8765 端口已有服务，但不是本快捷方式启动的 AgentBridge。'
        }
        Write-Host 'AgentBridge 已经在运行。' -ForegroundColor DarkGreen
    }
    else {
        $occupied = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
        if ($occupied) {
            throw '8765 端口已被其他程序占用。'
        }

        $startArgs = @{
            FilePath = $pythonPath
            ArgumentList = @('-m', 'uvicorn', 'agentbridge_server.app:app', '--host', '127.0.0.1', '--port', '8765')
            WorkingDirectory = $projectRoot
            WindowStyle = 'Hidden'
            RedirectStandardOutput = (Join-Path $logDir 'agentbridge.out.log')
            RedirectStandardError = (Join-Path $logDir 'agentbridge.err.log')
            PassThru = $true
        }
        $process = Start-Process @startArgs
        [IO.File]::WriteAllText($pidPath, [string]$process.Id)

        if (-not (Wait-ForHealth)) {
            $tail = Get-Content -LiteralPath (Join-Path $logDir 'agentbridge.err.log') -Tail 15 -ErrorAction SilentlyContinue
            throw "AgentBridge 没有按时启动。`n$($tail -join "`n")"
        }
        Write-Host 'AgentBridge 已启动。' -ForegroundColor Green
    }

    $status = Invoke-RestMethod -Uri $statusUrl -TimeoutSec 2
    if ($status.extension_online) {
        Write-Host 'Edge 扩展已连接。' -ForegroundColor Green
    }
    else {
        Write-Host 'Edge 扩展尚未连接：请确认扩展已侧载，并打开一个已登录的 chatgpt.com 标签页。' -ForegroundColor Yellow
    }

    if (-not $NoBrowser) {
        $edgeCandidates = @(
            "$env:ProgramFiles(x86)\Microsoft\Edge\Application\msedge.exe",
            "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe"
        )
        $edge = $edgeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
        if ($edge) {
            Start-Process -FilePath $edge -ArgumentList 'https://chatgpt.com/'
        }
        else {
            Start-Process 'https://chatgpt.com/'
        }
    }

    Write-Host ''
    Write-Host 'AgentBridge MCP：http://127.0.0.1:8765/mcp' -ForegroundColor Cyan
}
catch {
    Write-Host "启动失败：$($_.Exception.Message)" -ForegroundColor Red
    Write-Host "日志目录：$logDir" -ForegroundColor Yellow
    if (-not $NoPause) {
        Read-Host '按 Enter 关闭窗口'
    }
    exit 1
}
