<#
  Stop the Tibyan backend and frontend started by start.ps1.
  Only the processes recorded in .run\*.pid are stopped (PID and start time must both match),
  so unrelated Python or Node programs are never touched.

      powershell -ExecutionPolicy Bypass -File .\stop.ps1      (or double-click stop.cmd)
#>
param([switch]$Quiet)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\ps\common.ps1')

$stopped = 0
foreach ($n in @('frontend', 'backend')) {
    $pidFile = Join-Path $script:RunDir "$n.pid"
    $p = Get-TrackedProcess $n
    if ($null -ne $p) {
        if ($script:OnWindows) {
            # stop the tracked process and any child processes it started (e.g. build workers)
            & taskkill.exe /PID $p.Id /T /F | Out-Null
        } else {
            Stop-Process -Id $p.Id -ErrorAction SilentlyContinue
            try { $p.WaitForExit(10000) | Out-Null } catch {}
            if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
        }
        if (-not $Quiet) { Write-Host "Stopped $n (process $($p.Id))" }
        $stopped++
    } elseif ((Test-Path $pidFile) -and -not $Quiet) {
        Write-Host "$n was not running (stale record removed)"
    }
    if (Test-Path $pidFile) { Remove-Item $pidFile -Force }
}
if (-not $Quiet) {
    if ($stopped -eq 0) { Write-Host "Tibyan was not running." } else { Write-Host "Tibyan stopped." -ForegroundColor Green }
}
