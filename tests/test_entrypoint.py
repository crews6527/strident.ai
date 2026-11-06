"""Exercise main.main with real Qt, the real window and spawned task workers."""
import os
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class EntrypointTests(unittest.TestCase):
    def run_window(self, config=None):
        code = r'''
import json
import multiprocessing
import sys
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
import main

original_exec = QApplication.exec
outcome = {}
def exercise(app):
    window = app.activeWindow()
    if window is None:
        window = next(w for w in app.topLevelWidgets() if hasattr(w, 'controller'))
    commands = ['Help', '/testmodel', 'Help']
    window.submit(commands[0])
    timer = QTimer()
    timer.setInterval(50)
    def poll():
        records = list(window.records.values())
        if not records or records[-1]['status'] in {'queued', 'running'}:
            return
        if len(records) < len(commands):
            window.submit(commands[len(records)])
            return
        outcome['statuses'] = [r['status'] for r in records]
        outcome['failure'] = records[1]['summary']
        outcome['reply'] = records[1]['reply']
        outcome['rendered'] = not window.grab().isNull()
        timer.stop()
        window.close()
    timer.timeout.connect(poll)
    timer.start()
    QTimer.singleShot(20000, window.close)
    result = original_exec()
    outcome['thread_stopped'] = not window.controller.thread.is_alive()
    outcome['children'] = len(multiprocessing.active_children())
    return result
QApplication.exec = exercise
rc = main.main()
print(json.dumps(outcome))
assert rc == 0, rc
expected = sys.argv[1]
assert outcome.get('statuses') == ['complete', expected, 'complete'], outcome
if expected == 'failed':
    assert 'model' in outcome['failure'].lower(), outcome
else:
    assert outcome['reply'] == 'READY', outcome
assert outcome['rendered'] and outcome['thread_stopped'] and outcome['children'] == 0, outcome
'''
        with tempfile.TemporaryDirectory() as folder:
            if config:
                settings = Path(folder) / 'PromptCopyStudioAgent' / 'config.json'
                settings.parent.mkdir()
                settings.write_text(json.dumps(config), encoding='utf-8-sig')
            result = subprocess.run(
                [sys.executable, '-c', code, 'complete' if config else 'failed'],
                cwd=Path(__file__).resolve().parent.parent,
                env={**os.environ, 'LOCALAPPDATA': folder,
                     'QT_QPA_PLATFORM': os.environ.get('STRIDENT_TEST_QT_PLATFORM', 'offscreen')},
                text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


    def test_real_startup_tasks_failure_recovery_and_clean_shutdown(self):
        self.run_window()

    def test_real_window_spawned_worker_streaming_http_and_followup_task(self):
        requests = []
        class LocalOllama(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                requests.append(self.path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({'models': [{'name': 'fixture:1b'}]}).encode())
            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                requests.append((self.path, payload))
                self.send_response(200)
                self.end_headers()
                if self.path == '/api/show':
                    self.wfile.write(json.dumps({'capabilities': ['completion', 'thinking']}).encode())
                else:
                    for frame in ({'message': {'content': 'REA'}, 'done': False},
                                  {'message': {'content': 'DY'}, 'done': True}):
                        self.wfile.write((json.dumps(frame) + '\n').encode())
                        self.wfile.flush()
        server = ThreadingHTTPServer(('127.0.0.1', 0), LocalOllama)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self.run_window({'model': 'fixture:1b', 'ollama_url': f'http://127.0.0.1:{server.server_port}'})
            chat = [payload for item in requests if isinstance(item, tuple) for path, payload in [item] if path == '/api/chat']
            self.assertEqual(len(chat), 1)
            self.assertEqual(chat[0]['model'], 'fixture:1b')
            self.assertIs(chat[0]['think'], False)
            self.assertIs(chat[0]['stream'], True)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

class DiagnosticSelectionTests(unittest.TestCase):
    def test_command_line_probe_uses_saved_writing_model_and_bom_settings(self):
        import json
        from unittest.mock import patch
        import diagnose_ollama
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            path.write_text(json.dumps({'model': 'task:2b', 'text_model': 'writer:1b'}), encoding='utf-8-sig')
            original = path.read_bytes()
            with patch.object(diagnose_ollama, 'config_path', return_value=path), patch.object(
                    diagnose_ollama, 'run_check', return_value={'ok': True, 'reply': 'Hello', 'elapsed': 0.1}) as check:
                self.assertEqual(diagnose_ollama.main(), 0)
                self.assertEqual(check.call_args.args[0]['model'], 'writer:1b')
            self.assertEqual(path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
