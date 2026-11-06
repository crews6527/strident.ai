import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipIf(os.name == 'nt', 'POSIX launcher and symlink test')
class MacLauncherTests(unittest.TestCase):
    def test_desktop_symlink_uses_installation_with_spaces(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'Application folder'
            desktop = Path(folder) / 'Desktop'
            (root / '.venv/bin').mkdir(parents=True)
            desktop.mkdir()
            launcher = root / 'Launch-Strident.command'
            shutil.copyfile(Path(__file__).resolve().parents[1] / launcher.name, launcher)
            python = root / '.venv/bin/python'
            python.write_text('#!/bin/bash\npwd\nprintf "%s\\n" "$@"\n')
            python.chmod(0o755)
            shortcut = desktop / 'Strident.AI.command'
            shortcut.symlink_to(launcher)
            result = subprocess.run(['bash', str(shortcut)], cwd=desktop,
                                    text=True, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), [str(root.resolve()), '-I', 'guard_strident.py'])
