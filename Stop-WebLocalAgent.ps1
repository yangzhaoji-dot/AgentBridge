[CmdletBinding()]
param([switch]$NoPause)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$runtimeDir = Join-Path $projectRoot '.runtime'

function Get-OwnedProcess {
    param(
        [string]$PidFileName,
        [string]$ExpectedText
    )
    $pidPath = Join-Path $runtimeDir $PidFileName
    if (-not (Test-Path -LiteralPath $pidPath)) {
        return $null
    }
    $savedPid = [int](Get-Content -LiteralPath $pidPath -Raw).Trim()
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $savedPid" -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        return $null
    }
    if ($process.CommandLine -notlike "*$projectRoot*" -or $process.CommandLine -notlike "*$ExpectedText*") {
        throw "PID $savedPid 现在属于其他程序，已拒绝停止。"
    }
    return $process
}

function Stop-ProjectChildren {
    param([int]$ParentPid)
    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $ParentPid" -ErrorAction SilentlyContinue
    foreach ($child in $children) {
        if ($child.CommandLine -like "*$projectRoot*" -and $child.CommandLine -like '*codex*app-server*') {
            Stop-ProjectChildren -ParentPid $child.ProcessId
            Stop-Process -Id $child.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
}

function Stop-ProjectCodexProcesses {
    $codexProcesses = Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq 'node.exe' -and
        $_.CommandLine -like "*$projectRoot*" -and
        $_.CommandLine -like '*codex.js*app-server*'
    }
    foreach ($process in $codexProcesses) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

try {
    $connector = Get-OwnedProcess -PidFileName 'connector.pid' -ExpectedText 'local_connector.main'
    if ($connector) {
        Stop-ProjectChildren -ParentPid $connector.ProcessId
        Stop-Process -Id $connector.ProcessId -Force
        Write-Host '本地 Connector 已停止。' -ForegroundColor Green
    }
    else {
        Write-Host '本地 Connector 没有运行。'
    }
    Stop-ProjectCodexProcesses

    $relay = Get-OwnedProcess -PidFileName 'relay.pid' -ExpectedText 'relay_server.main'
    if ($relay) {
        Stop-Process -Id $relay.ProcessId -Force
        Write-Host '中转服务已停止。' -ForegroundColor Green
    }
    else {
        Write-Host '中转服务没有运行。'
    }

    foreach ($name in 'connector.pid', 'relay.pid') {
        $path = Join-Path $runtimeDir $name
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Force
        }
    }

    Write-Host 'Web Local Agent 已停止。' -ForegroundColor Cyan
}
catch {
    Write-Host "停止失败：$($_.Exception.Message)" -ForegroundColor Red
    if (-not $NoPause) {
        Read-Host '按 Enter 关闭窗口'
    }
    exit 1
}
