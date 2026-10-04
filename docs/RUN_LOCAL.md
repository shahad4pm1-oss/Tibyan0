# Run Tibyan on your computer

Written for someone who did not build the project. Windows first; Linux/macOS at the end.

## Prerequisites (install once)
1. **Python 3.11 (64-bit)** — https://www.python.org/downloads/ (or `winget install -e --id Python.Python.3.11`). During installation tick **"Add python.exe to PATH"**.
   **Recommended for competition: Python 3.11. Tested compatible: Python 3.11–3.14** (full backend test suite, corpus build and retrieval evaluations identical on 3.11, 3.12, 3.13 and 3.14). Setup prefers 3.11 when several versions are installed.
2. **Node.js 22 LTS** — https://nodejs.org/ (includes npm).
3. **PowerShell** — already part of Windows 10/11.
4. Internet access for the first setup only.

Put the project in a simple folder path, for example `C:\tibyan` (avoid very long paths; plain English folder names are safest).

## First time
Open the project folder in File Explorer and double-click **`setup.cmd`**, or in PowerShell:

```powershell
cd C:\tibyan
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

It checks Python and Node.js, installs everything, creates `.env`, downloads the verified source files, builds and validates the corpus, and ends with `SANITY CHECK PASSED` and `Setup complete.` (about 3–6 minutes the first time). Running it again is safe and fast.

## Run
Double-click **`start.cmd`**, or:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

It starts the backend and the frontend in the background, opens your browser, and prints:

```
Frontend URL : http://localhost:5173
Backend URL  : http://localhost:8000
Health URL   : http://localhost:8000/health
LLM mode     : LLM_UNAVAILABLE  (claim analysis off; quotes, sources, context and evidence work)
```

## Open
http://localhost:5173 — paste a quote and a claim, or click one of the example buttons.

## Stop
Double-click **`stop.cmd`**, or:

```powershell
powershell -ExecutionPolicy Bypass -File .\stop.ps1
```

Only the two processes started by `start.ps1` are stopped (recorded in `.run\`); other Python or Node programs are not touched.

## How to know everything works
- `start.ps1` prints `Tibyan is running.` and `Health : ok`.
- http://localhost:8000/health shows `"status":"ok"`, `quran_corpus.passages: 6236`, `hadith_corpus.passages: 10494`.
- In the app, the example **«اقتباس كامل»** shows «النص موجود بلفظه في المصدر» with سورة الفاتحة، الآية ٢, and **«حديث من الصحيحين»** shows صحيح البخاري، رقم ١.

## Optional: a real LLM (claim analysis)
Edit `.env` in the project folder (Notepad is fine):

```
LLM_PROVIDER=gemini        # or anthropic
LLM_MODEL=<a current model id>
LLM_API_KEY=<your key>
```

Save, then `stop.ps1` and `start.ps1`. The start screen shows `LLM mode : REAL_LLM`. The key stays only in `.env` (git-ignored); it is never printed or logged. Remove the three values to go back to `LLM_UNAVAILABLE`. Claim analysis needs internet; everything else works offline.

## Troubleshooting

| Problem | What to do |
|---|---|
| "running scripts is disabled on this system" | Use the `.cmd` files, or the `powershell -ExecutionPolicy Bypass -File ...` form shown above (it only affects that one command). |
| `No supported Python was found` | Install Python 3.11 from python.org with "Add python.exe to PATH", open a NEW PowerShell window, run setup again. If typing `python` opens the Microsoft Store, install from python.org instead. |
| `backend\.venv will be rebuilt: ...` | Not an error: the existing environment was made with another (or a broken) Python. Setup moves it aside, builds a new one, and restores the old one if anything fails. To keep a different supported version: `setup.ps1 -KeepVenv` (`./setup.sh --keep-venv`). Stop Tibyan first if it is running. |
| `Node.js was not found` / too old | Install Node.js 22 LTS, open a NEW PowerShell window, run setup again. |
| `Corpus build failed` (download) | Check the internet connection and run setup again. Or download the three files listed in the message (also in `docs\LOCAL_DATA_MANIFEST.md`) into `data\raw\kfgqpc\` and `data\raw\openiti\`, then run setup again. |
| Database validation error | `powershell -ExecutionPolicy Bypass -File .\setup.ps1 -Rebuild` |
| `Port 8000 / 5173 is already used` | Close the other program, or change `BACKEND_PORT` / `FRONTEND_PORT` in `.env`; if you change the frontend port, add `http://localhost:<port>` to `CORS_ORIGINS`. |
| `Tibyan is already running` | Open http://localhost:5173, or run `stop.ps1` first. |
| Page shows «تعذّر الوصول إلى خادم تبيان» | The backend is not running: run `start.ps1` again and read `logs\backend.err.log`. |
| Claim analysis says «تحليل الادعاء بالذكاء الاصطناعي غير متاح حالياً» | Normal without an LLM key. Add the key as above to enable it. |
| `search_mode: LEXICAL_ONLY` in health | Vector index files are missing: run `setup.ps1 -Rebuild`. The app still works. |
| Anything else | Look at `logs\backend.err.log` and `logs\frontend.err.log`. |

## Linux / macOS
```bash
./setup.sh      # once
./start.sh      # run
./stop.sh       # stop
```

## For developers
Tests: `powershell -ExecutionPolicy Bypass -File .\setup.ps1 -Dev`, then `backend\.venv\Scripts\python -m pytest` from `backend\`. Browser tests and evaluation scripts: `docs/OPERATIONS.md`, `docs/EVALUATION.md`.
