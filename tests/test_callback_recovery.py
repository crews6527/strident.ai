"""Real Qt callback errors must not abort the desktop process."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class CallbackRecoveryTests(unittest.TestCase):
    def run_recovery(self, failure):
        code = r'''
import sys
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox
import main
from unittest.mock import patch
original = QApplication.exec
previous_hook = sys.excepthook
outcome = []
def exercise(app):
    window = next(w for w in app.topLevelWidgets() if hasattr(w, 'controller'))
    def fail():
        if sys.argv[1] == 'health':
            with patch('pcs_agent.ui.psutil.cpu_percent', side_effect=RuntimeError('injected timer failure')):
                window.sample_health()
            assert not window.timer.isActive()
        else:
            raise RuntimeError('injected timer failure')
    def followup():
        for widget in app.topLevelWidgets():
            if isinstance(widget, QMessageBox):
                widget.accept()
        window.submit('Help')
    timer = QTimer()
    timer.setInterval(50)
    def poll():
        records = list(window.records.values())
        if records and records[-1]['status'] not in {'queued', 'running'}:
            outcome.append(records[-1]['status'])
            timer.stop()
            window.close()
    timer.timeout.connect(poll)
    timer.start()
    QTimer.singleShot(10, fail)
    QTimer.singleShot(100, followup)
    QTimer.singleShot(15000, window.close)
    result = original()
    assert not window.controller.thread.is_alive()
    return result
QApplication.exec = exercise
assert main.main() == 0
assert outcome == ['complete'], outcome
assert sys.excepthook is previous_hook
'''
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run([sys.executable, '-c', code, failure],
                cwd=Path(__file__).resolve().parent.parent,
                env={**os.environ, 'LOCALAPPDATA': folder, 'QT_QPA_PLATFORM': 'offscreen'},
                capture_output=True, text=True, timeout=25)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('injected timer failure', result.stderr)
        self.assertIn('Traceback', result.stderr)

    def test_timer_exception_then_real_task_and_shutdown(self):
        self.run_recovery('callback')

    def test_optional_health_failure_does_not_break_agent(self):
        self.run_recovery('health')
