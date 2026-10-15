"""Update a chosen local installation with backups and failure rollback."""
from __future__ import annotations
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

SOURCE = Path(__file__).resolve().parent


def manifest_files(source):
    manifest = source / 'SHA256SUMS.txt'
    files = {}
    for line in manifest.read_text(encoding='utf-8').splitlines():
        digest, relative = line.split('  ', 1)
        path = Path(relative)
        if path.is_absolute() or '..' in path.parts or relative in files:
            raise ValueError('Invalid package path.')
        if (len(path.parts) > 1 and path.parts[0] not in {'pcs_agent', 'assets', 'docs', 'licenses', 'tests', 'web'}) or (len(path.parts) == 1 and (path.suffix not in {'.py', '.cmd', '.ps1', '.md', '.txt'} or path.name.startswith('.'))):
            if relative != '.gitignore':
                raise ValueError('Package contains a non-source or private path: ' + relative)
        if path.parts[0] == 'web' and relative not in {'web/index.html', 'web/app.js', 'web/style.css'}:
            raise ValueError('Unexpected preview asset path: ' + relative)
        if not (source / path).resolve().is_relative_to(source.resolve()):
            raise ValueError('Package path escapes the source folder.')
        if hashlib.sha256((source / path).read_bytes()).hexdigest() != digest:
            raise ValueError('Package checksum failed: ' + relative)
        files[relative] = digest
    if not {'main.py', 'pcs_agent/runtime.py', 'pcs_agent/compliance.py', 'requirements.txt', 'verify_app.py'}.issubset(files):
        raise ValueError('The package is incomplete.')
    files['SHA256SUMS.txt'] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    return files


def interpreter(target):
    return target / ('.venv/Scripts/python.exe' if sys.platform == 'win32' else '.venv/bin/python')


def validate_target(target, files, source=SOURCE):
    target = Path(target).resolve()
    if target == source.resolve():
        raise ValueError('Select the existing installation, not the extracted update folder. To install a new copy, use Install-Strident.cmd.')
    for relative in ('main.py', 'Launch-Strident.cmd', 'pcs_agent/runtime.py'):
        if not (target / relative).is_file():
            raise ValueError('Select the existing Strident folder containing main.py, Launch-Strident.cmd and pcs_agent.')
    if not interpreter(target).is_file():
        raise ValueError('This installation has no virtual environment. Use Install-Strident.cmd in the new source folder instead.')
    for relative in files:
        if not (target / relative).resolve().is_relative_to(target):
            raise ValueError('An installed path resolves outside the chosen folder: ' + relative)
    return target


def check_not_running(target):
    code = '''import pathlib, psutil, sys
root=pathlib.Path(sys.argv[1]).resolve()
for p in psutil.process_iter():
    try:
        args=p.cmdline()
        if not any(pathlib.Path(a).name.lower() in {'main.py','live_preview.py','enable_phone.py','verify_idle.py','diagnose_ollama.py','diagnose_install.py','configure_fast_writing.py'} for a in args): continue
        if pathlib.Path(p.cwd()).resolve()==root or any(str(root).casefold() in a.casefold() for a in args):
            raise SystemExit('Close Strident and its diagnostics in this folder first. PID '+str(p.pid))
    except (psutil.NoSuchProcess,psutil.AccessDenied,psutil.ZombieProcess): pass
'''
    subprocess.run([str(interpreter(target)), '-c', code, str(target)], check=True, timeout=15)


def verify(target):
    python = str(interpreter(target))
    subprocess.run([python, '-c', 'import sys; assert sys.version_info[:2] == (3,12), "Python 3.12 is required"'], cwd=target, check=True, timeout=10)
    subprocess.run([python, '-m', 'pip', 'install', '-r', 'requirements.txt'], cwd=target, check=True, timeout=300)
    subprocess.run([python, '-m', 'pip', 'check'], cwd=target, check=True, timeout=30)
    subprocess.run([python, 'verify_app.py'], cwd=target, check=True, timeout=180)
    subprocess.run([python, 'diagnose_install.py', '--offline', '--output', str(target / 'backups/update-verification.json')], cwd=target, check=True, timeout=30)


def install(source, target, files, verifier=verify):
    if not (target / 'backups').resolve().is_relative_to(target.resolve()):
        raise ValueError('Backup folder resolves outside the installation.')
    backup = target / 'backups' / ('strident-3.3.0-' + datetime.now().strftime('%Y%m%d_%H%M%S') + '-' + uuid.uuid4().hex[:6])
    backup.mkdir(parents=True)
    if not backup.resolve().is_relative_to(target.resolve()):
        raise ValueError('Backup folder resolves outside the installation.')
    original = []
    for relative in files:
        path = target / relative
        if path.exists():
            if not path.is_file(): raise ValueError('Installed source path is not a file: ' + relative)
            saved = backup / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, saved)
            original.append(relative)
    (backup / 'restore-index.json').write_text(json.dumps({'original_files': original, 'new_files': [p for p in files if p not in original]}, indent=2), encoding='utf-8')
    changed = []
    try:
        for relative in files:
            path = target / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name(path.name + '.update-' + uuid.uuid4().hex[:8])
            try:
                shutil.copy2(source / relative, temp)
                temp.replace(path)
            finally:
                temp.unlink(missing_ok=True)
            changed.append(relative)
        verifier(target)
    except Exception:
        for relative in reversed(changed):
            if relative in original: shutil.copy2(backup / relative, target / relative)
            else: (target / relative).unlink(missing_ok=True)
        print('Source changes rolled back. Backup: ' + str(backup), flush=True)
        print('Dependencies installed by pip remain installed; personal settings/database were not part of this update.', flush=True)
        raise
    return backup


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', type=Path)
    args = parser.parse_args()
    try:
        files = manifest_files(SOURCE)
        target = validate_target(args.target or Path(input('Paste the EXISTING Strident folder containing main.py and .venv: ').strip().strip('"')), files)
        print('Updating this installation: ' + str(target), flush=True)
        check_not_running(target)
        backup = install(SOURCE, target, files)
        print('Source, installed tests and offline routing checks passed. Backup: ' + str(backup), flush=True)
        print('Launch this folder: ' + str(target / 'Launch-Strident.cmd'), flush=True)
        print('Confirm Strident.AI 3.2.3 in the title. Enter Check compliance. The logs must say Route: compliance checks.', flush=True)
        print('For the separate model problem, run Check-Strident.cmd in this installed folder and retain Strident_Diagnostics.json.', flush=True)
        return 0
    except Exception as exc:
        print('STOPPED: ' + str(exc), flush=True)
        return 1


if __name__ == '__main__': raise SystemExit(main())
