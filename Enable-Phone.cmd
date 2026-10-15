@echo off
pushd "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Run Install-Strident.cmd first.
 popd
 pause
 exit /b 1
)
".venv\Scripts\python.exe" enable_phone.py %*
set "strident_result=%ERRORLEVEL%"
popd
pause
exit /b %strident_result%
