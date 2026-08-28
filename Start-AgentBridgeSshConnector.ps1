[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SshHost,
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')]
    [Parameter(Mandatory = $true)]
    [string]$DeviceId,
    [ValidatePattern('^/[A-Za-z0-9._/-]+$')]
    [Parameter(Mandatory = $true)]
    [string]$RemoteEnvPath,
    [ValidateRange(1024, 65535)]
    [int]$LocalPort = 18765,
    [ValidateRange(1, 65535)]
    [int]$RemotePort = 8765,
    [switch]$NoPause
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot

try {
    & (Join-Path $projectRoot 'Start-AgentBridgeSshTunnel.ps1') `
        -SshHost $SshHost `
        -LocalPort $LocalPort `
        -RemotePort $RemotePort `
        -NoPause
    if ($LASTEXITCODE -ne 0) {
        throw 'SSH 隧道启动失败。'
    }

    $sshPath = (Get-Command ssh -ErrorAction Stop).Source
    $remotePython = @"
import json
import os
import sys

pairs = json.loads(os.environ['AGENTBRIDGE_PAIRINGS_JSON'])
token = pairs.get('$DeviceId')
if not isinstance(token, str) or len(token) < 32:
    raise SystemExit('required device pairing is unavailable')
sys.stdout.write(token)
"@
    $remoteCommand = "bash -lc 'source $RemoteEnvPath; exec python3 -'"
    $pairingToken = ($remotePython | & $sshPath `
        -o BatchMode=yes `
        -o StrictHostKeyChecking=yes `
        -o ConnectTimeout=12 `
        $SshHost $remoteCommand 2>$null).Trim()
    if ($LASTEXITCODE -ne 0 -or $pairingToken.Length -lt 32) {
        throw "无法读取设备 $DeviceId 的配对项。"
    }

    $oldUrl = $env:AGENTBRIDGE_REMOTE_WS_URL
    $oldToken = $env:AGENTBRIDGE_PAIRING_TOKEN
    $oldDevice = $env:AGENTBRIDGE_DEVICE_ID
    try {
        $env:AGENTBRIDGE_REMOTE_WS_URL = 'ws://127.0.0.1:{0}/ws/connector' -f $LocalPort
        $env:AGENTBRIDGE_PAIRING_TOKEN = $pairingToken
        $env:AGENTBRIDGE_DEVICE_ID = $DeviceId
        & (Join-Path $projectRoot 'Start-AgentBridgeConnector.ps1') -NoPause
        if ($LASTEXITCODE -ne 0) {
            throw '本机 Connector 启动失败。'
        }
    }
    finally {
        if ($null -eq $oldUrl) { Remove-Item Env:AGENTBRIDGE_REMOTE_WS_URL -ErrorAction SilentlyContinue } else { $env:AGENTBRIDGE_REMOTE_WS_URL = $oldUrl }
        if ($null -eq $oldToken) { Remove-Item Env:AGENTBRIDGE_PAIRING_TOKEN -ErrorAction SilentlyContinue } else { $env:AGENTBRIDGE_PAIRING_TOKEN = $oldToken }
        if ($null -eq $oldDevice) { Remove-Item Env:AGENTBRIDGE_DEVICE_ID -ErrorAction SilentlyContinue } else { $env:AGENTBRIDGE_DEVICE_ID = $oldDevice }
    }
}
catch {
    Write-Host "启动失败：$($_.Exception.Message)" -ForegroundColor Red
    if (-not $NoPause) {
        Read-Host '按 Enter 关闭窗口'
    }
    exit 1
}
