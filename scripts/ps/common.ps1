# Shared helpers for setup.ps1 / start.ps1 / stop.ps1.
# Compatible with Windows PowerShell 5.1 and PowerShell 7+ (Windows, Linux, macOS).

$script:OnWindows = ($env:OS -eq 'Windows_NT')
$script:Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$script:RunDir = Join-Path $script:Root '.run'
$script:LogDir = Join-Path $script:Root 'logs'

function Write-Step([string]$msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg)   { Write-Host "    OK  $msg" -ForegroundColor Green }
function Write-Warn2([string]$msg) { Write-Host "    !!  $msg" -ForegroundColor Yellow }
function Stop-WithMessage([string]$msg) {
    Write-Host ""
    Write-Host "STOPPED: $msg" -ForegroundColor Red
    Write-Host ""
    exit 1
}

function Get-VenvPython {
    if ($script:OnWindows) { return (Join-Path $script:Root 'backend\.venv\Scripts\python.exe') }
    return (Join-Path $script:Root 'backend/.venv/bin/python')
}

function Get-NpmCommand { if ($script:OnWindows) { 'npm.cmd' } else { 'npm' } }

# Read KEY=VALUE pairs from .env (falls back to .env.example). Inline " # comments" are removed.
function Read-DotEnv {
    $vals = @{}
    $file = Join-Path $script:Root '.env'
    if (-not (Test-Path $file)) { $file = Join-Path $script:Root '.env.example' }
    if (-not (Test-Path $file)) { return $vals }
    foreach ($line in Get-Content -Path $file -Encoding UTF8) {
        $t = $line.Trim()
        if ($t -eq '' -or $t.StartsWith('#')) { continue }
        $i = $t.IndexOf('=')
        if ($i -lt 1) { continue }
        $k = $t.Substring(0, $i).Trim()
        $v = $t.Substring($i + 1)
        $c = $v.IndexOf(' #')
        if ($c -ge 0) { $v = $v.Substring(0, $c) }
        $vals[$k] = $v.Trim().Trim('"').Trim("'")
    }
    return $vals
}

function Get-Setting($envVals, [string]$key, [string]$default) {
    if ($envVals.ContainsKey($key) -and $envVals[$key] -ne '') { return $envVals[$key] }
    return $default
}

# True if nothing is listening on 127.0.0.1:<port>.
function Test-PortFree([int]$port) {
    $listener = $null
    try {
        $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Parse('127.0.0.1'), $port)
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        if ($null -ne $listener) { try { $listener.Stop() } catch {} }
    }
}

function Wait-Http([string]$url, [int]$seconds) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5
            if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) { return $true }
        } catch {}
        Start-Sleep -Milliseconds 700
    }
    return $false
}

# PID files hold "<pid> <process start time ticks>" so stop.ps1 never kills an unrelated process
# that happens to reuse the PID.
function Save-ProcInfo([string]$name, $proc) {
    if (-not (Test-Path $script:RunDir)) { New-Item -ItemType Directory -Path $script:RunDir | Out-Null }
    $p = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
    $ticks = 0
    if ($null -ne $p) { try { $ticks = $p.StartTime.ToUniversalTime().Ticks } catch { $ticks = 0 } }
    Set-Content -Path (Join-Path $script:RunDir "$name.pid") -Value "$($proc.Id) $ticks" -Encoding Ascii
}

function Get-TrackedProcess([string]$name) {
    $f = Join-Path $script:RunDir "$name.pid"
    if (-not (Test-Path $f)) { return $null }
    $parts = (Get-Content -Path $f -Raw).Trim().Split(' ')
    $procId = [int]$parts[0]
    $ticks = [long]$parts[1]
    $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($null -eq $p) { return $null }
    if ($ticks -ne 0) {
        try {
            $now = $p.StartTime.ToUniversalTime().Ticks
            if ([math]::Abs($now - $ticks) -gt 20000000) { return $null }   # >2 s apart: a different process
        } catch {}
    }
    return $p
}
