@echo off
REM Double-click or run from a terminal. Runs stop.ps1 with a process-only execution policy bypass.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop.ps1" %*
if /I not "%TIBYAN_NO_PAUSE%"=="1" pause
