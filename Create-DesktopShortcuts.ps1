$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$desktop = [Environment]::GetFolderPath('Desktop')
$powerShellPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
if (-not (Test-Path -LiteralPath $powerShellPath)) {
    throw "找不到 Windows PowerShell：$powerShellPath"
}
$shell = New-Object -ComObject WScript.Shell

$items = @(
    @{
        Name = '启动 Web Local Agent.lnk'
        Script = 'Start-WebLocalAgent.ps1'
        Description = '启动本地 Agent、中转服务并打开网页'
        Icon = "$env:SystemRoot\System32\shell32.dll,220"
    },
    @{
        Name = '停止 Web Local Agent.lnk'
        Script = 'Stop-WebLocalAgent.ps1'
        Description = '停止 Web Local Agent 后台进程'
        Icon = "$env:SystemRoot\System32\shell32.dll,131"
    },
    @{
        Name = '启动 AgentBridge.lnk'
        Script = 'Start-AgentBridge.ps1'
        Description = '启动 Codex 到 Edge ChatGPT 的 MCP 桥'
        Icon = "$env:SystemRoot\System32\shell32.dll,220"
    },
    @{
        Name = '停止 AgentBridge.lnk'
        Script = 'Stop-AgentBridge.ps1'
        Description = '停止 AgentBridge MCP 服务'
        Icon = "$env:SystemRoot\System32\shell32.dll,131"
    }
)

foreach ($item in $items) {
    $shortcutPath = Join-Path $desktop $item.Name
    $scriptPath = Join-Path $projectRoot $item.Script
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $powerShellPath
    $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""
    $shortcut.WorkingDirectory = $projectRoot
    $shortcut.Description = $item.Description
    $shortcut.IconLocation = $item.Icon
    $shortcut.WindowStyle = 1
    $shortcut.Save()
    Write-Host "已创建：$shortcutPath"
}
