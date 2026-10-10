@echo off
pushd "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run Install-Strident.cmd first.
  pause
  popd
  exit /b 1
)
".venv\Scripts\python.exe" verify_idle.py --seconds 30
pause
popd
