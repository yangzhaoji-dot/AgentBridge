[CmdletBinding()]
param(
    [string]$Proxy,
    [switch]$SkipDesktopShortcuts,
    [switch]$NoPause
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$venvPath = Join-Path $projectRoot '.venv'
$venvPython = Join-Path $venvPath 'Scripts\python.exe'
$requirementsPath = Join-Path $projectRoot 'requirements.txt'

function Stop-WithMessage {
    param([string]$Message)
    Write-Host "安装失败：$Message" -ForegroundColor Red
    if (-not $NoPause) {
        Read-Host '按 Enter 关闭窗口'
    }
    exit 1
}

try {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($null -eq $py) {
        throw '未找到 Python Launcher（py）。请先安装 Python 3.12。'
    }
    & py -3.12 --version
    if ($LASTEXITCODE -ne 0) {
        throw '未找到 Python 3.12。请安装后重新运行。'
    }

    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if ($null -eq $npm) {
        throw '未找到 npm。请先安装 Node.js LTS。'
    }
    if (-not (Test-Path -LiteralPath $requirementsPath)) {
        throw "找不到依赖文件：$requirementsPath"
    }

    Write-Host '创建 Python 虚拟环境…'
    & py -3.12 -m venv $venvPath
    if ($LASTEXITCODE -ne 0) {
        throw '无法创建 Python 虚拟环境。'
    }

    $pipArgs = @('-m', 'pip', 'install', '-r', $requirementsPath)
    if ($Proxy) {
        $pipArgs = @('-m', 'pip', 'install', '--proxy', $Proxy, '-r', $requirementsPath)
    }
    Write-Host '安装 Python 依赖…'
    & $venvPython @pipArgs
    if ($LASTEXITCODE -ne 0) {
        throw 'Python 依赖安装失败。'
    }

    $npmArgs = @('install')
    if ($Proxy) {
        $npmArgs += @('--proxy', $Proxy)
    }
    Write-Host '安装 Node.js 依赖…'
    Push-Location $projectRoot
    try {
        & npm @npmArgs
        if ($LASTEXITCODE -ne 0) {
            throw 'Node.js 依赖安装失败。'
        }
    }
    finally {
        Pop-Location
    }

    if (-not $SkipDesktopShortcuts) {
        & (Join-Path $projectRoot 'Create-AgentBridgeShortcuts.ps1')
    }

    Write-Host ''
    Write-Host 'AgentBridge 安装完成。' -ForegroundColor Green
    Write-Host '下一步：在 Edge 打开 edge://extensions，加载 extension 文件夹。'
    Write-Host '随后双击桌面的“启动 AgentBridge”。'
}
catch {
    Stop-WithMessage $_.Exception.Message
}
