@echo off
pushd "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Run Install-Strident.cmd first.
 popd
 pause
 exit /b 1
)
".venv\Scripts\python.exe" live_preview.py
set "strident_result=%ERRORLEVEL%"
popd
if not "%strident_result%"=="0" pause
exit /b %strident_result%
