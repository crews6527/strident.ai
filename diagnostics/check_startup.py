"""Diagnose an existing installation without resetting settings or launching Qt."""
import os
from pathlib import Path
import subprocess
import sys

PROBE = r'''
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
print('STEP 1: Import installed application', flush=True)
from pcs_agent import __version__
from pcs_agent.config import load
from pcs_agent.instance import InstanceLock
print('Installed build: ' + __version__, flush=True)
print('STEP 2: Load saved settings (no reset)', flush=True)
config = load()
print('PASS: Saved settings loaded', flush=True)
print('STEP 3: Open data folder and check instance lock', flush=True)
lock = InstanceLock(config['data_dir'])
try:
    print('PASS: Instance lock acquired', flush=True)
finally:
    lock.close()
print('STARTUP CHECK PASSED. Settings and lock did not reproduce exit code 2.', flush=True)
'''


def probe(root, interpreter):
    return subprocess.run([str(interpreter), '-I', '-c', PROBE, str(root)],
                          cwd=root, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=30,
                          env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})


def main():
    default = Path.home() / 'Downloads' / 'strident.ai-strident.ai' / 'strident.ai-strident.ai'
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    if not (root / 'guard_strident.py').is_file():
        root = Path(input('Paste the folder containing Launch-Strident.cmd: ').strip().strip('"'))
    interpreter = root / '.venv' / 'Scripts' / 'python.exe'
    report = Path(__file__).resolve().parent / 'Strident-Startup-Result.txt'
    lines = ['Strident startup diagnostic', 'Installation: ' + str(root)]
    code = 1
    try:
        if not (root / 'pcs_agent' / 'config.py').is_file():
            raise RuntimeError('Application files were not found in the selected folder.')
        if not interpreter.is_file():
            raise RuntimeError('The installation has no .venv\\Scripts\\python.exe.')
        result = probe(root, interpreter)
        lines.extend([result.stdout, result.stderr, 'Diagnostic exit code: ' + str(result.returncode)])
        code = result.returncode
    except Exception as exc:
        lines.append(type(exc).__name__ + ': ' + str(exc))
    text = '\n'.join(lines)
    print(text, flush=True)
    try:
        report.write_text(text + '\n', encoding='utf-8')
        print('Send this file: ' + str(report), flush=True)
    except OSError as exc:
        print('Could not save report; copy the visible output: ' + str(exc), flush=True)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
