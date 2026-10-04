<#
  Tibyan one-time setup (Windows PowerShell 5.1+ / PowerShell 7+).

  Run from the project folder:
      powershell -ExecutionPolicy Bypass -File .\setup.ps1
  or double-click setup.cmd.

  What it does (safe to run again):
    1. checks Python (3.11 recommended and preferred; 3.12, 3.13 and 3.14 also supported) and Node.js 20.19+/22.12+
    2. creates backend\.venv and installs pinned Python packages. An existing backend\.venv is checked first:
       if its Python does not run, is unsupported, or differs from the selected Python, it is rebuilt safely
       (the old one is kept aside and restored if the rebuild fails)
    3. installs pinned frontend packages (npm ci)
    4. creates .env from .env.example if missing (no secrets added)
    5. downloads the verified source files (Quran: KFGQPC package; hadith: OpenITI files) and builds the
       corpus database, search indexes and vector index; validates everything
    6. runs a sanity check (one Quran and one hadith lookup)

  Options:
    -Rebuild    rebuild the corpus database even if a valid one exists
    -Dev        also install test tools (pytest, ruff)
    -KeepVenv   keep an existing backend\.venv that uses a different SUPPORTED Python version than the one selected
#>
param([switch]$Rebuild, [switch]$Dev, [switch]$KeepVenv)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\ps\common.ps1')
Set-Location $script:Root
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

Write-Host ""
Write-Host "Tibyan setup" -ForegroundColor White
Write-Host "Project folder: $script:Root"
Write-Host ""

# ---------------------------------------------------------------- 1. Python
# Recommended for the competition build: 3.11 (tried first). Tested compatible: 3.11-3.14.
$SupportedPython = @('3.11', '3.12', '3.13', '3.14')
Write-Step "Checking Python (3.11 recommended; 3.12, 3.13 and 3.14 also supported)"
$candidates = @()
if ($script:OnWindows) {
    foreach ($sv in $SupportedPython) { $candidates += ,@('py', "-$sv") }
    $candidates += ,@('python'); $candidates += ,@('python3')
} else {
    foreach ($sv in $SupportedPython) { $candidates += ,@("python$sv") }
    $candidates += ,@('python3')
}
$pyCmd = $null
foreach ($c in $candidates) {
    $exe = $c[0]
    $pre = @(); if ($c.Count -gt 1) { $pre = $c[1..($c.Count - 1)] }
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    try {
        $v = & $exe @pre -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and ($v -in $SupportedPython)) { $pyCmd = $c; $pyVer = $v; Write-Ok "Python $v ($($c -join ' '))"; break }
    } catch {}
}
if ($null -eq $pyCmd) {
    Stop-WithMessage "No supported Python was found (3.11 recommended; 3.12, 3.13 or 3.14 also work). Install Python 3.11 (64-bit) from https://www.python.org/downloads/ ; during installation tick 'Add python.exe to PATH' (the 'py' launcher is installed by default). Then run setup.ps1 again."
}
if ($pyVer -ne '3.11') { Write-Warn2 "Using Python $pyVer (supported). Python 3.11 is the recommended version for the competition build." }

# ---------------------------------------------------------------- 2. Node.js
Write-Step "Checking Node.js (20.19+ or 22.12+) and npm"
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Stop-WithMessage "Node.js was not found. Install the LTS version (22.x) from https://nodejs.org/ , then open a NEW PowerShell window and run setup.ps1 again."
}
$nodeV = (& node --version).Trim().TrimStart('v')
$np = $nodeV.Split('.'); $maj = [int]$np[0]; $min = [int]$np[1]
if (-not (($maj -eq 20 -and $min -ge 19) -or ($maj -eq 22 -and $min -ge 12) -or ($maj -ge 23) -or ($maj -eq 21))) {
    Stop-WithMessage "Node.js $nodeV is too old. Install Node.js 22 LTS from https://nodejs.org/ and run setup.ps1 again."
}
$npm = Get-NpmCommand
if (-not (Get-Command $npm -ErrorAction SilentlyContinue)) { Stop-WithMessage "npm was not found (it is installed together with Node.js). Reinstall Node.js 22 LTS." }
Write-Ok "Node.js $nodeV"

# ---------------------------------------------------------------- 3. Python environment
$venvDir = Join-Path $script:Root 'backend/.venv'
$venvPy = Get-VenvPython
$script:OldVenv = $null      # previous backend\.venv kept aside during a rebuild
$script:OldVenvVer = $null
$venvVer = $pyVer

# Restore the previous environment if a rebuild fails, then stop.
function Stop-Python([string]$msg) {
    if ($script:OldVenv -and (Test-Path $script:OldVenv)) {
        if (Test-Path $venvDir) { Remove-Item -Recurse -Force $venvDir -ErrorAction SilentlyContinue }
        Move-Item -Path $script:OldVenv -Destination $venvDir
        Write-Warn2 "The previous backend\.venv (Python $($script:OldVenvVer)) was restored unchanged."
    }
    Stop-WithMessage $msg
}

if (Test-Path $venvDir) {
    Write-Step "Checking the existing Python environment backend\.venv"
    $vv = $null
    try {
        if (-not (Test-Path $venvPy)) { throw "no interpreter" }
        $vv = & $venvPy -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null | Select-Object -First 1
        if ($LASTEXITCODE -ne 0) { $vv = $null }
    } catch { $vv = $null }
    $why = $null
    if (-not $vv) { $why = "its Python does not run (the Python it was created with may have been removed or moved)" }
    elseif ($vv -notin $SupportedPython) { $why = "it uses Python $vv, which Tibyan does not support" }
    elseif ($vv -ne $pyVer) {
        if ($KeepVenv) { Write-Warn2 "backend\.venv uses Python $vv, not the selected Python ${pyVer}: kept because of -KeepVenv."; $venvVer = $vv }
        else { $why = "it uses Python $vv, but setup selected Python $pyVer" }
    } else { Write-Ok "backend\.venv uses Python $vv" }
    if ($why) {
        Write-Warn2 "backend\.venv will be rebuilt: $why."
        if ($vv -and ($vv -in $SupportedPython)) { Write-Warn2 "To keep Python $vv instead, run: setup.ps1 -KeepVenv   (or: setup.cmd -KeepVenv)" }
        $tracked = Get-TrackedProcess 'backend'
        if ($null -ne $tracked) { Stop-WithMessage "Tibyan is running from this environment. Stop it first (stop.cmd or stop.ps1), then run setup again." }
        if (-not (Test-Path $script:RunDir)) { New-Item -ItemType Directory -Path $script:RunDir | Out-Null }
        $script:OldVenv = Join-Path $script:RunDir 'venv-previous'
        if (Test-Path $script:OldVenv) { Remove-Item -Recurse -Force $script:OldVenv }
        try { Move-Item -Path $venvDir -Destination $script:OldVenv -ErrorAction Stop }
        catch { $script:OldVenv = $null; Stop-WithMessage "Could not move the old backend\.venv aside (a file in it may be in use). Close programs using it, or delete backend\.venv yourself, then run setup again." }
        $script:OldVenvVer = if ($vv) { $vv } else { 'unknown' }
    }
}
if (-not (Test-Path $venvDir)) {
    Write-Step "Creating Python virtual environment backend\.venv (Python $pyVer)"
    $exe = $pyCmd[0]; $pre = @(); if ($pyCmd.Count -gt 1) { $pre = $pyCmd[1..($pyCmd.Count - 1)] }
    & $exe @pre -m venv $venvDir
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPy)) { Stop-Python "Could not create the virtual environment in backend\.venv." }
}
Write-Step "Installing Python packages (pinned; first time takes a few minutes)"
& $venvPy -m pip install --disable-pip-version-check -q -r (Join-Path $script:Root 'backend/requirements.txt') -c (Join-Path $script:Root 'backend/constraints.txt')
if ($LASTEXITCODE -ne 0) { Stop-Python "Python package installation failed (see the messages above). Check your internet connection and run setup.ps1 again." }
if ($Dev) {
    & $venvPy -m pip install --disable-pip-version-check -q -r (Join-Path $script:Root 'backend/requirements-dev.txt') -c (Join-Path $script:Root 'backend/constraints.txt')
    if ($LASTEXITCODE -ne 0) { Stop-Python "Installing test tools failed." }
}
& $venvPy -c "import sqlite3; c=sqlite3.connect(':memory:'); c.execute('create virtual table t using fts5(x)')"
if ($LASTEXITCODE -ne 0) { Stop-Python "This Python's SQLite has no FTS5 support. Install the official Python 3.11 from python.org." }
if ($script:OldVenv -and (Test-Path $script:OldVenv)) {
    Remove-Item -Recurse -Force $script:OldVenv -ErrorAction SilentlyContinue
    Write-Ok "backend\.venv rebuilt with Python $pyVer (previous environment removed)"
    $script:OldVenv = $null
}
Write-Ok "Python packages installed (Python $venvVer)"

# ---------------------------------------------------------------- 4. Frontend packages
$lockHash = (Get-FileHash -Algorithm SHA256 (Join-Path $script:Root 'frontend/package-lock.json')).Hash
$stamp = Join-Path $script:Root 'frontend/node_modules/.tibyan-lock-sha256'
if ((Test-Path $stamp) -and ((Get-Content $stamp -Raw).Trim() -eq $lockHash) -and (Test-Path (Join-Path $script:Root 'frontend/node_modules/vite/bin/vite.js'))) {
    Write-Ok "Frontend packages already installed (package-lock.json unchanged)"
} else {
    Write-Step "Installing frontend packages (npm ci)"
    Push-Location (Join-Path $script:Root 'frontend')
    try {
        & $npm ci --no-audit --no-fund --loglevel=error
        if ($LASTEXITCODE -ne 0) { Stop-WithMessage "npm ci failed (see above). Check your internet connection and run setup.ps1 again." }
    } finally { Pop-Location }
    Set-Content -Path $stamp -Value $lockHash -Encoding Ascii
    Write-Ok "Frontend packages installed"
}

# ---------------------------------------------------------------- 5. .env and folders
if (-not (Test-Path (Join-Path $script:Root '.env'))) {
    Copy-Item (Join-Path $script:Root '.env.example') (Join-Path $script:Root '.env')
    Write-Ok "Created .env from .env.example (no LLM key: the app runs in LLM_UNAVAILABLE mode)"
} else { Write-Ok ".env already exists (left unchanged)" }
foreach ($d in @('data/raw', 'data/indexes', 'logs', '.run')) {
    $p = Join-Path $script:Root $d
    if (-not (Test-Path $p)) { New-Item -ItemType Directory -Path $p | Out-Null }
}

# ---------------------------------------------------------------- 6. Corpus
$db = Join-Path $script:Root 'data/indexes/tibyan.sqlite3'
$needBuild = $Rebuild -or -not (Test-Path $db)
if (-not $needBuild) {
    Write-Step "Validating the existing corpus database"
    & $venvPy (Join-Path $script:Root 'scripts/validate_corpus.py') | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Warn2 "Existing database failed validation: rebuilding"; $needBuild = $true }
    else { Write-Ok "Existing corpus database is valid" }
}
if ($needBuild) {
    Write-Step "Downloading verified source files and building the corpus (about 1 minute)"
    & $venvPy (Join-Path $script:Root 'scripts/build_corpus.py')
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "The corpus could not be built. Most often the source files could not be downloaded." -ForegroundColor Red
        Write-Host "Each file is accepted only if its SHA-256 matches. You can place them manually and run setup.ps1 again:" -ForegroundColor Yellow
        Write-Host "  1) data\raw\kfgqpc\UthmanicHafs_v2-0.zip"
        Write-Host "     from https://raw.githubusercontent.com/quranpedia/quran-text/87d7691a0179dbb3cadbc2276581f0fdbbe476b1/sources/kfgqpc/UthmanicHafs_v2-0.zip"
        Write-Host "  2) data\raw\openiti\0256Bukhari.Sahih.Shamela0001681-ara1"
        Write-Host "     from https://raw.githubusercontent.com/OpenITI/0275AH/44e1c36738a2bf5c14dafa232a6ae1891e6171cd/data/0256Bukhari/0256Bukhari.Sahih/0256Bukhari.Sahih.Shamela0001681-ara1"
        Write-Host "  3) data\raw\openiti\0261Muslim.Sahih.Shamela0001727-ara1.mARkdown"
        Write-Host "     from https://raw.githubusercontent.com/OpenITI/0275AH/44e1c36738a2bf5c14dafa232a6ae1891e6171cd/data/0261Muslim/0261Muslim.Sahih/0261Muslim.Sahih.Shamela0001727-ara1.mARkdown"
        Write-Host "  Expected SHA-256 values: docs\LOCAL_DATA_MANIFEST.md"
        Stop-WithMessage "Corpus build failed. Fix the item above, then run setup.ps1 again."
    }
    Write-Ok "Corpus built and validated"
}

# ---------------------------------------------------------------- 7. Sanity check
Write-Step "Sanity check (one Quran lookup, one hadith lookup, no LLM)"
& $venvPy (Join-Path $script:Root 'scripts/sanity_check.py')
if ($LASTEXITCODE -ne 0) { Stop-WithMessage "Sanity check failed (see above). Run setup.ps1 -Rebuild." }

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Start Tibyan with:   powershell -ExecutionPolicy Bypass -File .\start.ps1   (or double-click start.cmd)"
Write-Host ""
