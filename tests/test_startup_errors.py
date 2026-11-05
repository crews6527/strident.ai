import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class StartupErrorTests(unittest.TestCase):
    def check_error(self, setup, expected, code):
        script = '''
from unittest.mock import patch
from PyQt6.QtWidgets import QMessageBox
import main
with patch.object(QMessageBox, 'critical', return_value=None):
''' + setup + '''
    raise SystemExit(main.main())
'''
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run([sys.executable, '-c', script],
                cwd=Path(__file__).resolve().parent.parent,
                env={**os.environ, 'LOCALAPPDATA': folder, 'QT_QPA_PLATFORM': 'offscreen'},
                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertIn(expected, result.stderr)
        self.assertIn('Traceback', result.stderr)

    def test_settings_failure_is_logged_without_relying_on_dialog(self):
        self.check_error("    import pcs_agent.config\n    pcs_agent.config.load = lambda: (_ for _ in ()).throw(ValueError('invalid saved configuration'))\n", 'loading saved settings', 2)

    def test_lock_failure_is_logged_without_relying_on_dialog(self):
        self.check_error("    import pcs_agent.instance\n    pcs_agent.instance.InstanceLock = lambda _: (_ for _ in ()).throw(RuntimeError('Strident is already running'))\n", 'acquiring the instance lock', 2)

    def test_window_failure_is_logged_without_relying_on_dialog(self):
        self.check_error("    import pcs_agent.ui\n    pcs_agent.ui.ConsoleWindow = lambda _: (_ for _ in ()).throw(RuntimeError('window construction failed'))\n", 'opening the desktop window', 1)
