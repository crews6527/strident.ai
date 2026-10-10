@echo off
pushd "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run Install-Strident.cmd first.
  pause
  popd
  exit /b 1
)
".venv\Scripts\python.exe" configure_fast_writing.py
pause
popd
