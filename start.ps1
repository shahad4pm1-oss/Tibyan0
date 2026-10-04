<#
  Start Tibyan locally (backend API + frontend) in the background.

      powershell -ExecutionPolicy Bypass -File .\start.ps1      (or double-click start.cmd)

  Stop it with stop.ps1. Logs: logs\backend.*.log, logs\frontend.*.log
  Ports and options come from .env (BACKEND_PORT, FRONTEND_PORT, OPEN_BROWSER).
#>
param([switch]$NoBrowser)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\ps\common.ps1')
Set-Location $script:Root

$cfg = Read-DotEnv
$bHost = Get-Setting $cfg 'BACKEND_HOST' '127.0.0.1'
$bPort = [int](Get-Setting $cfg 'BACKEND_PORT' '8000')
$fPort = [int](Get-Setting $cfg 'FRONTEND_PORT' '5173')
$openBrowser = ((Get-Setting $cfg 'OPEN_BROWSER' 'true') -eq 'true') -and -not $NoBrowser
$backendUrl = "http://localhost:$bPort"
$frontendUrl = "http://localhost:$fPort"

Write-Host ""
Write-Host "Starting Tibyan" -ForegroundColor White

# ---------------------------------------------------------------- checks
$venvPy = Get-VenvPython
if (-not (Test-Path $venvPy)) { Stop-WithMessage "Python environment not found. Run setup first:  powershell -ExecutionPolicy Bypass -File .\setup.ps1" }
if (-not (Test-Path (Join-Path $script:Root 'frontend/node_modules/vite/bin/vite.js'))) { Stop-WithMessage "Frontend packages not installed. Run setup.ps1 first." }
if (-not (Test-Path (Join-Path $script:Root 'data/indexes/tibyan.sqlite3'))) { Stop-WithMessage "Corpus database data\indexes\tibyan.sqlite3 not found. Run setup.ps1 first." }
foreach ($f in @('semantic.faiss', 'semantic_ids.json', 'semantic_meta.json', 'lsa_model.npz')) {
    if (-not (Test-Path (Join-Path $script:Root "data/indexes/$f"))) {
        Write-Warn2 "Vector index file data\indexes\$f is missing: search runs in LEXICAL_ONLY mode (run setup.ps1 -Rebuild to restore)."
    }
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { Stop-WithMessage "Node.js not found. Install Node.js 22 LTS and run setup.ps1." }

$already = @()
foreach ($n in @('backend', 'frontend')) { if ($null -ne (Get-TrackedProcess $n)) { $already += $n } }
if ($already.Count -gt 0) {
    Stop-WithMessage "Tibyan is already running ($($already -join ', ')). Open $frontendUrl , or stop it first with stop.ps1."
}
if (-not (Test-PortFree $bPort)) { Stop-WithMessage "Port $bPort (backend) is already used by another program. Close it, or set BACKEND_PORT to another number in .env (and add the frontend origin to CORS_ORIGINS if you also change FRONTEND_PORT)." }
if (-not (Test-PortFree $fPort)) { Stop-WithMessage "Port $fPort (frontend) is already used by another program. Close it, or set FRONTEND_PORT in .env and add http://localhost:<new port> to CORS_ORIGINS." }

foreach ($d in @($script:LogDir, $script:RunDir)) { if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d | Out-Null } }

# ---------------------------------------------------------------- backend
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$hidden = @{}
if ($script:OnWindows) { $hidden = @{ WindowStyle = 'Hidden' } }
$backend = Start-Process -FilePath $venvPy -PassThru @hidden `
    -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', $bHost, '--port', "$bPort", '--no-server-header') `
    -WorkingDirectory (Join-Path $script:Root 'backend') `
    -RedirectStandardOutput (Join-Path $script:LogDir 'backend.out.log') `
    -RedirectStandardError (Join-Path $script:LogDir 'backend.err.log')
Save-ProcInfo 'backend' $backend
Write-Step "Backend starting (process $($backend.Id))"

# ---------------------------------------------------------------- frontend (Vite dev server, API URL from BACKEND_PORT)
$env:VITE_API_BASE_URL = $backendUrl
$vite = Join-Path $script:Root 'frontend/node_modules/vite/bin/vite.js'
$frontend = Start-Process -FilePath 'node' -PassThru @hidden `
    -ArgumentList @($vite, '--port', "$fPort", '--strictPort', '--host', '127.0.0.1') `
    -WorkingDirectory (Join-Path $script:Root 'frontend') `
    -RedirectStandardOutput (Join-Path $script:LogDir 'frontend.out.log') `
    -RedirectStandardError (Join-Path $script:LogDir 'frontend.err.log')
Save-ProcInfo 'frontend' $frontend
Write-Step "Frontend starting (process $($frontend.Id))"

# ---------------------------------------------------------------- wait and report
if (-not (Wait-Http "http://127.0.0.1:$bPort/health" 90)) {
    Write-Host "Backend did not start. Last lines of logs\backend.err.log:" -ForegroundColor Red
    Get-Content (Join-Path $script:LogDir 'backend.err.log') -Tail 25 -ErrorAction SilentlyContinue
    & (Join-Path $script:Root 'stop.ps1') -Quiet
    Stop-WithMessage "Backend failed to start (see above)."
}
if (-not (Wait-Http "http://127.0.0.1:$fPort/" 60)) {
    Write-Host "Frontend did not start. Last lines of logs\frontend.err.log:" -ForegroundColor Red
    Get-Content (Join-Path $script:LogDir 'frontend.err.log') -Tail 25 -ErrorAction SilentlyContinue
    & (Join-Path $script:Root 'stop.ps1') -Quiet
    Stop-WithMessage "Frontend failed to start (see above)."
}
$h = Invoke-RestMethod -Uri "http://127.0.0.1:$bPort/health" -TimeoutSec 10
$c = $h.components

Write-Host ""
Write-Host "Tibyan is running." -ForegroundColor Green
Write-Host ""
Write-Host "  Frontend URL : $frontendUrl"
Write-Host "  Backend URL  : $backendUrl"
Write-Host "  Health URL   : $backendUrl/health"
Write-Host ""
Write-Host "  Health       : $($h.status)   (version $($h.app_version), $($h.app_env))"
Write-Host "  Quran        : $($c.quran_corpus.passages) ayat ($($c.quran_corpus.status))"
Write-Host "  Hadith       : $($c.hadith_corpus.passages) records ($($c.hadith_corpus.status))"
Write-Host "  Search mode  : $($h.search_mode)"
if ($h.llm_mode -eq 'REAL_LLM') {
    Write-Host "  LLM mode     : REAL_LLM ($($c.llm.provider) / $($c.llm.model))" -ForegroundColor Green
} else {
    Write-Host "  LLM mode     : $($h.llm_mode)  (claim analysis off; quotes, sources, context and evidence work)" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "  Stop with    : powershell -ExecutionPolicy Bypass -File .\stop.ps1   (or double-click stop.cmd)"
Write-Host ""
if ($openBrowser -and $script:OnWindows) { Start-Process $frontendUrl }
