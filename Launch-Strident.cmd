@echo off
setlocal
pushd "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo The dedicated Python environment is missing. Run Recover-Strident.cmd.
  pause
  popd
  exit /b 1
)
".venv\Scripts\python.exe" -I guard_strident.py
set "STRIDENT_EXIT=%ERRORLEVEL%"
if not "%STRIDENT_EXIT%"=="0" pause
popd
exit /b %STRIDENT_EXIT%
