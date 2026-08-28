[CmdletBinding()]
param(
    [string]$ProfilePath,
    [string]$SshHost,
    [string]$DeviceId,
    [string]$RemoteEnvPath,
    [int]$LocalPort = 0,
    [int]$RemotePort = 0,
    [switch]$NoPause
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
. (Join-Path $projectRoot 'AgentBridgeSshProfile.ps1')

try {
    $profile = Get-AgentBridgeSshProfile $ProfilePath
    if ([string]::IsNullOrWhiteSpace($SshHost) -and $null -ne $profile) { $SshHost = $profile.ssh_host }
    if ([string]::IsNullOrWhiteSpace($DeviceId) -and $null -ne $profile) { $DeviceId = $profile.device_id }
    if ([string]::IsNullOrWhiteSpace($RemoteEnvPath) -and $null -ne $profile) { $RemoteEnvPath = $profile.remote_env_path }
    if ($LocalPort -eq 0) { $LocalPort = if ($null -ne $profile) { [int]$profile.local_port } else { 18765 } }
    if ($RemotePort -eq 0) { $RemotePort = if ($null -ne $profile) { [int]$profile.remote_port } else { 8765 } }
    Assert-AgentBridgeSshConnection `
        -SshHost $SshHost `
        -DeviceId $DeviceId `
        -RemoteEnvPath $RemoteEnvPath `
        -LocalPort $LocalPort `
        -RemotePort $RemotePort

    & (Join-Path $projectRoot 'Start-AgentBridgeSshTunnel.ps1') `
        -SshHost $SshHost `
        -LocalPort $LocalPort `
        -RemotePort $RemotePort `
        -NoPause

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
