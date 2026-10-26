@echo off
cd /d "%~dp0"
set /p "STRIDENT_ADMIN_NAME=Choose administrator username: "
"%~dp0.venv\Scripts\python.exe" manage_accounts.py create-admin "%STRIDENT_ADMIN_NAME%"
pause
