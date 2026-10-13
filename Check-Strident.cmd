@echo off
pushd "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run Install-Strident.cmd in this folder first.
  pause
  popd
  exit /b 1
)
".venv\Scripts\python.exe" diagnose_install.py %*
pause
popd
