[CmdletBinding()]
param([string]$ProfilePath)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'AgentBridgeSshProfile.ps1')

try {
    $profile = Get-AgentBridgeSshProfile $ProfilePath
    if ($null -eq $profile) {
        throw '未找到 SSH 配置。请先运行 Set-AgentBridgeSshProfile.ps1。'
    }
    Assert-AgentBridgeSshProfile `
        -SshHost $profile.ssh_host `
        -DeviceId $profile.device_id `
        -RemoteEnvPath $profile.remote_env_path `
        -RemoteProjectPath $profile.remote_project_path `
        -LocalPort ([int]$profile.local_port) `
        -RemotePort ([int]$profile.remote_port)

    $connectorStatus = $null
    $relayStatus = $null
    try { $connectorStatus = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/status' -TimeoutSec 2 } catch {}
    try {
        $relayUrl = 'http://127.0.0.1:{0}/api/status' -f $profile.local_port
        $relayStatus = Invoke-RestMethod -Uri $relayUrl -TimeoutSec 2
    }
    catch {}

    [PSCustomObject]@{
        ssh_host = $profile.ssh_host
        device_id = $profile.device_id
        tunnel_relay_reachable = $null -ne $relayStatus
        local_connector_running = $null -ne $connectorStatus
        remote_connected = $connectorStatus.remote_connected
        extension_online = $connectorStatus.extension_online
        server_connector_count = $relayStatus.connector_count
    } | Format-List
}
catch {
    Write-Host "状态检查失败：$($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
