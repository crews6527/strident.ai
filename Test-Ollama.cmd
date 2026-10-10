@echo off
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Run Install-Strident.cmd first.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0diagnose_ollama.py"
echo.
echo If this fails, copy the FAILED message and last stage for troubleshooting.
pause
