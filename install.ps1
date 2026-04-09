param(
    [string]$TargetDir = $PSScriptRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Write-Info([string]$message) {
    Write-Host $message -ForegroundColor Cyan
}

function Write-ErrorAndExit([string]$message) {
    Write-Host "ERROR: $message" -ForegroundColor Red
    exit 1
}

$target = if ([string]::IsNullOrWhiteSpace($TargetDir)) { $root } else { Resolve-Path -Path $TargetDir | Select-Object -ExpandProperty Path }

$pythonCmd = if (Get-Command python3 -ErrorAction SilentlyContinue) { 'python3' } elseif (Get-Command python -ErrorAction SilentlyContinue) { 'python' } else { $null }
if (-not $pythonCmd) {
    Write-ErrorAndExit 'Python 3 is required. Install Python 3 and rerun this script.'
}

try {
    & $pythonCmd -c 'import sys; assert sys.version_info >= (3,8)'
} catch {
    Write-ErrorAndExit "Python 3.8+ is required. Detected: $(& $pythonCmd --version 2>&1 | Select-Object -First 1)"
}

if (-not (Test-Path '.\code-hacker-skills.agent.md')) {
    Write-ErrorAndExit 'Manifest file code-hacker-skills.agent.md not found in repository root.'
}

if (-not (Test-Path '.\skills')) {
    Write-ErrorAndExit 'skills directory not found in repository root.'
}

if ($target -ne $root) {
    Write-Info "Installing custom agent files into: $target"
    if (-not (Test-Path $target)) {
        New-Item -ItemType Directory -Path $target | Out-Null
    }
    Copy-Item -Path '.\code-hacker-skills.agent.md' -Destination $target -Force
    $destSkills = Join-Path $target 'skills'
    if (Test-Path $destSkills) {
        Remove-Item -Recurse -Force $destSkills
    }
    Copy-Item -Path '.\skills' -Destination $target -Recurse -Force
    Write-Info 'Copied manifest and skills/ into target workspace.'
} else {
    Write-Info 'Running install validation in current repo root.'
}

Write-Info "Python OK: $(& $pythonCmd --version 2>&1 | Select-Object -First 1)"

$codeCmd = Get-Command code -ErrorAction SilentlyContinue
if ($codeCmd) {
    $extensions = & code --list-extensions
    if ($extensions -match 'github.copilot-chat') {
        Write-Info 'VS Code CLI and GitHub Copilot Chat extension are installed.'
    } else {
        Write-Info 'GitHub Copilot Chat extension is not installed.'
        $choice = Read-Host 'Install it now with VS Code CLI? [y/N]'
        if ($choice -match '^[Yy]$') {
            & code --install-extension GitHub.copilot-chat
            Write-Info 'Installed GitHub Copilot Chat extension.'
        }
    }
} else {
    Write-Info "VS Code CLI ('code') is not available."
    Write-Info "Open VS Code and install the 'code' command from the Command Palette."
}

Write-Info 'Install script complete.'
Write-Info "Open $target in VS Code and load code-hacker-skills.agent.md as a custom Copilot Chat agent."
