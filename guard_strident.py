"""Explicit launch guard. Detect accidental changes; never terminate other apps."""
from __future__ import annotations
import argparse
from datetime import datetime
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parent
# Clear only the child environment. Never change the user's Windows settings.
CONFLICTING = {'PYTHONHOME', 'PYTHONPATH', 'PYTHONSTARTUP', 'QT_PLUGIN_PATH',
               'QT_QPA_PLATFORM_PLUGIN_PATH', 'QT_QPA_PLATFORM', 'QT_QPA_PLATFORMTHEME',
               'QT_STYLE_OVERRIDE', 'QML2_IMPORT_PATH', 'QML_IMPORT_PATH'}


def clean_environment(source=None):
    return {k: v for k, v in (os.environ if source is None else source).items()
            if k.upper() not in CONFLICTING}


def check_integrity(root=ROOT):
    root = Path(root).resolve()
    manifest = root / 'SHA256SUMS.txt'
    entries = {}
    for line in manifest.read_text(encoding='utf-8').splitlines():
        digest, relative = line.split('  ', 1)
        path = Path(relative)
        target = root / path
        if (not re.fullmatch(r'[a-f0-9]{64}', digest) or path.is_absolute()
                or '..' in path.parts or '\\' in relative or ':' in relative
                or relative in entries or not target.resolve().is_relative_to(root)):
            raise ValueError('Invalid integrity manifest entry.')
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise RuntimeError('Missing or changed application file: ' + relative +
                               '. Re-extract the verified recovery package into a separate folder; your data is not reset.')
        entries[relative] = digest
    required = {'main.py', 'guard_strident.py', 'requirements.txt', 'pcs_agent/runtime.py', 'pcs_agent/ui.py'}
    if not required.issubset(entries):
        raise RuntimeError('Incomplete application manifest.')
    # Extra Python files can shadow standard-library or installed packages.
    for path in root.glob('*.py'):
        if path.name not in entries:
            raise RuntimeError('Unexpected Python file in application folder: ' + path.name)
    for path in (root / 'pcs_agent').rglob('*.py'):
        if path.relative_to(root).as_posix() not in entries:
            raise RuntimeError('Unexpected agent module: ' + path.relative_to(root).as_posix())
    return len(entries)


def check_dependencies(root=ROOT):
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError('Use the dedicated Python 3.12 environment. Run Recover-Strident.cmd.')
    for line in (Path(root) / 'requirements.txt').read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        name, version = line.strip().split('==', 1)
        try:
            actual = metadata.version(name)
        except metadata.PackageNotFoundError:
            raise RuntimeError('Missing dependency: ' + name + '. Run Recover-Strident.cmd.') from None
        if actual != version:
            raise RuntimeError(f'Dependency changed: {name}; expected {version}, found {actual}. Run Recover-Strident.cmd.')


def child_main():
    # -I removes global PYTHONPATH and user packages; add only verified app code.
    check_integrity()
    check_dependencies()
    sys.path.insert(0, str(ROOT))
    import multiprocessing
    multiprocessing.freeze_support()
    from main import main
    return main()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--integrity', action='store_true', help='Check only package files before installing dependencies')
    parser.add_argument('--check', action='store_true', help='Check files, dependencies and configuration without starting inference')
    parser.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.integrity:
        print('Verified application files:', check_integrity())
        return 0
    if args.child:
        return child_main()
    log_root = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'PromptCopyStudioAgent' / 'startup-logs'
    log_root.mkdir(parents=True, exist_ok=True)
    log = log_root / (datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.log')
    with log.open('w', encoding='utf-8') as stream:
        try:
            count = check_integrity()
            check_dependencies()
            stream.write(f'Checked {count} application files. Python: {sys.executable}\n')
            stream.write('Isolated startup; conflicting Python/Qt variables removed for this launch only.\n')
            stream.flush()
            if args.check:
                sys.path.insert(0, str(ROOT))
                from pcs_agent.config import config_path, validate
                settings = config_path()
                if settings.exists() and settings.stat().st_size > 128000:
                    raise ValueError('Configuration exceeds 128 KB. Preserve it for inspection.')
                validate(json.loads(settings.read_text(encoding='utf-8-sig')) if settings.exists() else {})
                print('PASS: package integrity, pinned dependencies and configuration. No model or task was run.')
                return 0
            result = subprocess.run([sys.executable, '-I', str(Path(__file__).resolve()), '--child'],
                                    cwd=ROOT, env=clean_environment(), stdout=stream, stderr=subprocess.STDOUT)
            stream.write(f'\nApplication exit code: {result.returncode}\n')
            code = result.returncode
        except Exception:
            traceback.print_exc(file=stream)
            code = 1
    if code:
        print('Strident did not start or exited with an error. Diagnostic log: ' + str(log))
        print('Your settings and projects were not reset. Read the log before repairing.')
        print(log.read_text(encoding='utf-8', errors='replace')[-6000:])
    return code


if __name__ == '__main__':
    raise SystemExit(main())
