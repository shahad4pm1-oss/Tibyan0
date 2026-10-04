@echo off
REM Double-click or run from a terminal. Runs setup.ps1 with a process-only execution policy bypass.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
if /I not "%TIBYAN_NO_PAUSE%"=="1" pause
