[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SshHost,
    [ValidateRange(1024, 65535)]
    [int]$LocalPort = 18765,
    [ValidateRange(1, 65535)]
    [int]$RemotePort = 8765,
    [switch]$NoPause
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$runtimeDir = Join-Path $projectRoot '.runtime'
$logDir = Join-Path $runtimeDir 'logs'
$pidPath = Join-Path $runtimeDir 'agentbridge-ssh-tunnel.pid'
$metadataPath = Join-Path $runtimeDir 'agentbridge-ssh-tunnel.json'
$portForward = '127.0.0.1:{0}:127.0.0.1:{1}' -f $LocalPort, $RemotePort
$healthUrl = 'http://127.0.0.1:{0}/api/health' -f $LocalPort

function Test-TunnelHealth {
    try {
        return (Invoke-RestMethod -Uri $healthUrl -TimeoutSec 1).status -eq 'ok'
    }
    catch {
        return $false
    }
}

try {
    $sshPath = (Get-Command ssh -ErrorAction Stop).Source
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null

    if (Test-TunnelHealth) {
        if (-not (Test-Path -LiteralPath $pidPath) -or -not (Test-Path -LiteralPath $metadataPath)) {
            $matching = @(Get-CimInstance Win32_Process | Where-Object {
                $_.Name -ieq 'ssh.exe' -and
                $_.CommandLine -like "*$portForward*" -and
                $_.CommandLine -like "*$SshHost*"
            })
            if ($matching.Count -eq 1) {
                [IO.File]::WriteAllText($pidPath, [string]$matching[0].ProcessId)
                @{ SshHost = $SshHost; LocalPort = $LocalPort; RemotePort = $RemotePort } |
                    ConvertTo-Json -Compress |
                    Set-Content -LiteralPath $metadataPath -NoNewline
            }
        }
        Write-Host "AgentBridge SSH 隧道已可用：$healthUrl" -ForegroundColor DarkGreen
        return
    }

    if (Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue) {
        throw "本机 $LocalPort 端口已被其他程序占用。"
    }

    $sshArguments = @(
        '-N',
        '-L', $portForward,
        '-o', 'BatchMode=yes',
        '-o', 'StrictHostKeyChecking=yes',
        '-o', 'ConnectTimeout=12',
        '-o', 'ExitOnForwardFailure=yes',
        '-o', 'ServerAliveInterval=30',
        '-o', 'ServerAliveCountMax=3',
        $SshHost
    )
    $process = Start-Process -FilePath $sshPath `
        -ArgumentList $sshArguments `
        -WindowStyle Hidden `
        -PassThru `
        -RedirectStandardOutput (Join-Path $logDir 'agentbridge-ssh-tunnel.out.log') `
        -RedirectStandardError (Join-Path $logDir 'agentbridge-ssh-tunnel.err.log')

    [IO.File]::WriteAllText($pidPath, [string]$process.Id)
    @{ SshHost = $SshHost; LocalPort = $LocalPort; RemotePort = $RemotePort } |
        ConvertTo-Json -Compress |
        Set-Content -LiteralPath $metadataPath -NoNewline

    for ($attempt = 0; $attempt -lt 80; $attempt++) {
        if (Test-TunnelHealth) { break }
        if ($process.HasExited) {
            throw 'SSH 隧道进程已退出。请检查 .runtime\logs\agentbridge-ssh-tunnel.err.log。'
        }
        Start-Sleep -Milliseconds 125
    }
    if (-not (Test-TunnelHealth)) {
        throw 'SSH 隧道没有按时连接到服务器 Relay。'
    }

    Write-Host "AgentBridge SSH 隧道已启动：$healthUrl" -ForegroundColor Green
}
catch {
    Write-Host "启动失败：$($_.Exception.Message)" -ForegroundColor Red
    if (-not $NoPause) {
        Read-Host '按 Enter 关闭窗口'
    }
    exit 1
}
