@echo off
REM Double-click this, or run "run.bat" from any terminal.
REM It bypasses PowerShell's script-execution policy and calls run.ps1.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
