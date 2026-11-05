@echo off
setlocal
py -3.12 -I "%~dp0check_startup.py"
echo.
echo The diagnostic is finished. Send Strident-Startup-Result.txt from this folder.
echo If that file was not created, send a screenshot of this window.
pause
