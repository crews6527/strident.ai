#!/bin/bash
set -e
cd -- "$(dirname -- "$0")"
finish() {
    status=$?
    if [ "$status" -ne 0 ]; then
        echo 'Installation stopped. Your settings and projects were not reset.'
        read -r -p 'Press Return to close. ' _ || true
    fi
    exit "$status"
}
trap finish EXIT
if ! command -v python3.12 >/dev/null 2>&1; then
    echo 'Python 3.12 is required. Install it from python.org, reopen Terminal, and run this installer again.'
    exit 1
fi
python3.12 -I guard_strident.py --integrity
if [ ! -d .venv ]; then
    python3.12 -m venv .venv
fi
.venv/bin/python -c 'import sys; assert sys.version_info[:2] == (3, 12), "This .venv uses another Python version. Install into a fresh folder."'
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
.venv/bin/python -I guard_strident.py --check
chmod +x Launch-Strident.command Install-Strident.command
shortcut="$HOME/Desktop/Strident.AI.command"
if [ -d "$HOME/Desktop" ] && { [ ! -e "$shortcut" ] || [ -L "$shortcut" ]; }; then
    ln -sfn "$PWD/Launch-Strident.command" "$shortcut"
    echo "Desktop launcher: $shortcut"
fi
echo 'Installation checks passed. Launch with: bash Launch-Strident.command'
echo 'Model generation has not been tested by this installer.'
