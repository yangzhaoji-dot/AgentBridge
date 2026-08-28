[CmdletBinding()]
param(
    [string]$ProfilePath,
    [string]$Prompt = '请只回复 AgentBridge SSH smoke test OK。'
)

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
    if ($Prompt.Length -gt 5000) { throw '测试提示词不能超过 5000 个字符。' }

    $sshPath = (Get-Command ssh -ErrorAction Stop).Source
    $encodedPrompt = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Prompt))
    $remoteCommand = "cd $($profile.remote_project_path) && .venv/bin/python -m scripts.smoke_remote_agentbridge --device-id $($profile.device_id) --prompt-base64 $encodedPrompt"
    & $sshPath -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=12 $profile.ssh_host $remoteCommand
    if ($LASTEXITCODE -ne 0) { throw '服务器 smoke 测试失败。' }
}
catch {
    Write-Host "测试失败：$($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
