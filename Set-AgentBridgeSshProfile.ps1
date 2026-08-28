[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SshHost,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')]
    [string]$DeviceId,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^/[A-Za-z0-9._/-]+$')]
    [string]$RemoteEnvPath,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^/[A-Za-z0-9._/-]+$')]
    [string]$RemoteProjectPath,
    [ValidateRange(1024, 65535)]
    [int]$LocalPort = 18765,
    [ValidateRange(1, 65535)]
    [int]$RemotePort = 8765,
    [string]$ProfilePath
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'AgentBridgeSshProfile.ps1')

$resolvedPath = Get-AgentBridgeSshProfilePath $ProfilePath
Assert-AgentBridgeSshProfile `
    -SshHost $SshHost `
    -DeviceId $DeviceId `
    -RemoteEnvPath $RemoteEnvPath `
    -RemoteProjectPath $RemoteProjectPath `
    -LocalPort $LocalPort `
    -RemotePort $RemotePort

New-Item -ItemType Directory -Path (Split-Path -Parent $resolvedPath) -Force | Out-Null
@{
    ssh_host = $SshHost
    device_id = $DeviceId
    remote_env_path = $RemoteEnvPath
    remote_project_path = $RemoteProjectPath
    local_port = $LocalPort
    remote_port = $RemotePort
} | ConvertTo-Json | Set-Content -LiteralPath $resolvedPath -NoNewline

Write-Host "AgentBridge SSH 配置已保存：$resolvedPath" -ForegroundColor Green
Write-Host '配置不包含配对令牌。' -ForegroundColor DarkGreen
