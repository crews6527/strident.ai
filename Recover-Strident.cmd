@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Recover-Strident.ps1"
set "STRIDENT_EXIT=%ERRORLEVEL%"
pause
exit /b %STRIDENT_EXIT%
