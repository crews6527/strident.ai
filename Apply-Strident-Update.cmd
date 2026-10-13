@echo off
pushd "%~dp0"
py -3.12 apply_update.py
pause
popd
