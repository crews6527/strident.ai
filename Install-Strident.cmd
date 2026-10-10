@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-Strident.ps1"
if errorlevel 1 echo Installation stopped. Review the error above.
pause
