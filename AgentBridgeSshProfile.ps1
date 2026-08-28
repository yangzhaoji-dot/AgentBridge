function Get-AgentBridgeSshProfilePath {
    param([string]$ProfilePath)

    if (-not [string]::IsNullOrWhiteSpace($ProfilePath)) {
        return [IO.Path]::GetFullPath($ProfilePath)
    }
    $base = [Environment]::GetFolderPath('LocalApplicationData')
    return (Join-Path $base 'AgentBridge\ssh-profile.json')
}

function Get-AgentBridgeSshProfile {
    param([string]$ProfilePath)

    $resolvedPath = Get-AgentBridgeSshProfilePath $ProfilePath
    if (-not (Test-Path -LiteralPath $resolvedPath -PathType Leaf)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $resolvedPath -Raw | ConvertFrom-Json
    }
    catch {
        throw "SSH 配置文件无法读取：$resolvedPath"
    }
}

function Assert-AgentBridgeSshConnection {
    param(
        [string]$SshHost,
        [string]$DeviceId,
        [string]$RemoteEnvPath,
        [int]$LocalPort,
        [int]$RemotePort
    )

    if ([string]::IsNullOrWhiteSpace($SshHost)) {
        throw '缺少 SSH 主机。请先运行 Set-AgentBridgeSshProfile.ps1。'
    }
    if ($SshHost -notmatch '^[A-Za-z0-9][A-Za-z0-9._@-]{0,127}$') {
        throw 'SSH 主机格式无效。'
    }
    if ($DeviceId -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$') {
        throw '设备 ID 只能包含字母、数字、点、下划线和连字符。'
    }
    if ($RemoteEnvPath -notmatch '^/[A-Za-z0-9._/-]+$') {
        throw '远程配对配置路径格式无效。'
    }
    if ($LocalPort -lt 1024 -or $LocalPort -gt 65535) {
        throw '本地隧道端口必须在 1024 到 65535 之间。'
    }
    if ($RemotePort -lt 1 -or $RemotePort -gt 65535) {
        throw '服务器 Relay 端口必须在 1 到 65535 之间。'
    }
}

function Assert-AgentBridgeSshProfile {
    param(
        [string]$SshHost,
        [string]$DeviceId,
        [string]$RemoteEnvPath,
        [string]$RemoteProjectPath,
        [int]$LocalPort,
        [int]$RemotePort
    )

    Assert-AgentBridgeSshConnection `
        -SshHost $SshHost `
        -DeviceId $DeviceId `
        -RemoteEnvPath $RemoteEnvPath `
        -LocalPort $LocalPort `
        -RemotePort $RemotePort
    if ($RemoteProjectPath -notmatch '^/[A-Za-z0-9._/-]+$') {
        throw '远程项目路径格式无效。'
    }
}
