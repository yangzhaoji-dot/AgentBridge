[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$NoPause
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$runtimeDir = Join-Path $projectRoot '.runtime'
$logDir = Join-Path $runtimeDir 'logs'
$tokenPath = Join-Path $runtimeDir 'relay-token.txt'
$relayPidPath = Join-Path $runtimeDir 'relay.pid'
$connectorPidPath = Join-Path $runtimeDir 'connector.pid'
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$codexPath = Join-Path $projectRoot 'node_modules\.bin\codex.cmd'
$deviceId = 'local-dev'
$relayUrl = 'http://127.0.0.1:8000'

function Show-Failure {
    param([string]$Message)
    Write-Host ''
    Write-Host "启动失败：$Message" -ForegroundColor Red
    Write-Host "日志目录：$logDir" -ForegroundColor Yellow
    if (-not $NoPause) {
        Read-Host '按 Enter 关闭窗口'
    }
}

function Test-RelayHealth {
    try {
        $result = Invoke-RestMethod -Uri "$relayUrl/api/health" -TimeoutSec 1
        return $result.status -eq 'ok'
    }
    catch {
        return $false
    }
}

function Test-AgentOnline {
    try {
        $result = Invoke-RestMethod -Uri "$relayUrl/api/status/$deviceId" -TimeoutSec 1
        return [bool]$result.agent_online
    }
    catch {
        return $false
    }
}

function Wait-ForCondition {
    param(
        [scriptblock]$Condition,
        [int]$Attempts = 60,
        [int]$DelayMilliseconds = 250
    )
    for ($attempt = 0; $attempt -lt $Attempts; $attempt++) {
        if (& $Condition) {
            return $true
        }
        Start-Sleep -Milliseconds $DelayMilliseconds
    }
    return $false
}

function Test-OwnedPid {
    param(
        [string]$PidPath,
        [string]$ExpectedText
    )
    if (-not (Test-Path -LiteralPath $PidPath)) {
        return $false
    }
    $savedPid = [int](Get-Content -LiteralPath $PidPath -Raw).Trim()
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $savedPid" -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        return $false
    }
    return $process.CommandLine -like "*$projectRoot*" -and $process.CommandLine -like "*$ExpectedText*"
}

try {
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        throw "找不到 Python 虚拟环境：$pythonPath"
    }
    if (-not (Test-Path -LiteralPath $codexPath)) {
        throw "找不到项目内 Codex：$codexPath"
    }

    New-Item -ItemType Directory -Path $logDir -Force | Out-Null

    if (Test-Path -LiteralPath $tokenPath) {
        $token = (Get-Content -LiteralPath $tokenPath -Raw).Trim()
    }
    else {
        $tokenBytes = New-Object byte[] 32
        $random = [Security.Cryptography.RandomNumberGenerator]::Create()
        try {
            $random.GetBytes($tokenBytes)
        }
        finally {
            $random.Dispose()
        }
        $token = -join ($tokenBytes | ForEach-Object { $_.ToString('X2') })
        [IO.File]::WriteAllText(
            $tokenPath,
            $token,
            (New-Object -TypeName System.Text.UTF8Encoding -ArgumentList $false)
        )
    }
    if ([string]::IsNullOrWhiteSpace($token)) {
        throw '配对口令文件为空。'
    }

    $env:RELAY_SHARED_TOKEN = $token
    $env:NO_PROXY = '127.0.0.1,localhost'

    $proxyListener = Get-NetTCPConnection -LocalPort 12000 -State Listen -ErrorAction SilentlyContinue
    if ($proxyListener) {
        $env:HTTP_PROXY = 'http://127.0.0.1:12000'
        $env:HTTPS_PROXY = 'http://127.0.0.1:12000'
    }

    if (Test-RelayHealth) {
        if (-not (Test-OwnedPid -PidPath $relayPidPath -ExpectedText 'relay_server.main')) {
            throw '8000 端口已有服务，但不是本快捷方式启动的中转服务。'
        }
        Write-Host '中转服务已经在运行。' -ForegroundColor DarkGreen
    }
    else {
        $occupied = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
        if ($occupied) {
            throw '8000 端口已被其他程序占用。'
        }

        $relayStart = @{
            FilePath = $pythonPath
            ArgumentList = @('-m', 'uvicorn', 'relay_server.main:app', '--host', '127.0.0.1', '--port', '8000')
            WorkingDirectory = $projectRoot
            WindowStyle = 'Hidden'
            RedirectStandardOutput = (Join-Path $logDir 'relay.out.log')
            RedirectStandardError = (Join-Path $logDir 'relay.err.log')
            PassThru = $true
        }
        $relayProcess = Start-Process @relayStart
        [IO.File]::WriteAllText($relayPidPath, [string]$relayProcess.Id)

        if (-not (Wait-ForCondition -Condition { Test-RelayHealth })) {
            $tail = Get-Content -LiteralPath (Join-Path $logDir 'relay.err.log') -Tail 12 -ErrorAction SilentlyContinue
            throw "中转服务没有按时启动。`n$($tail -join "`n")"
        }
        Write-Host '中转服务已启动。' -ForegroundColor Green
    }

    if (Test-AgentOnline) {
        Write-Host '本地 Connector 已经在线。' -ForegroundColor DarkGreen
    }
    else {
        $env:RELAY_URL = 'ws://127.0.0.1:8000/ws'
        $env:LOCAL_AGENT_DEVICE_ID = $deviceId
        $env:LOCAL_AGENT_DEFAULT_CWD = $projectRoot
        $env:LOCAL_AGENT_ALLOWED_ROOTS = (Join-Path $env:USERPROFILE 'Documents\Codex')
        $env:CODEX_BIN = $codexPath

        $connectorStart = @{
            FilePath = $pythonPath
            ArgumentList = @('-m', 'local_connector.main')
            WorkingDirectory = $projectRoot
            WindowStyle = 'Hidden'
            RedirectStandardOutput = (Join-Path $logDir 'connector.out.log')
            RedirectStandardError = (Join-Path $logDir 'connector.err.log')
            PassThru = $true
        }
        $connectorProcess = Start-Process @connectorStart
        [IO.File]::WriteAllText($connectorPidPath, [string]$connectorProcess.Id)

        if (-not (Wait-ForCondition -Condition { Test-AgentOnline } -Attempts 100)) {
            $tail = Get-Content -LiteralPath (Join-Path $logDir 'connector.err.log') -Tail 12 -ErrorAction SilentlyContinue
            throw "Connector 没有按时上线。`n$($tail -join "`n")"
        }
        Write-Host '本地 Connector 已启动。' -ForegroundColor Green
    }

    if (-not $NoBrowser) {
        $encodedToken = [Uri]::EscapeDataString($token)
        $browserUrl = "$relayUrl/#token=$encodedToken&device=$deviceId&autoconnect=1"
        Start-Process $browserUrl
    }

    Write-Host ''
    Write-Host 'Web Local Agent 已准备好。' -ForegroundColor Cyan
    Write-Host "网页地址：$relayUrl"
}
catch {
    Show-Failure -Message $_.Exception.Message
    exit 1
}
