#!/bin/bash
# Finder and Terminal use the same installation and isolated Python launcher.
source_path="${BASH_SOURCE[0]}"
while [ -L "$source_path" ]; do
    source_dir=$(cd -P -- "$(dirname -- "$source_path")" && pwd) || exit 1
    source_path=$(readlink "$source_path") || exit 1
    case "$source_path" in /*) ;; *) source_path="$source_dir/$source_path" ;; esac
done
cd -P -- "$(dirname -- "$source_path")" || exit 1
if [ ! -x .venv/bin/python ]; then
    echo 'The Python environment is missing. Run: bash Install-Strident.command'
    read -r -p 'Press Return to close. ' _
    exit 1
fi
.venv/bin/python -I guard_strident.py
status=$?
if [ "$status" -ne 0 ]; then
    read -r -p 'Startup failed. Keep the log shown above. Press Return to close. ' _
fi
exit "$status"
