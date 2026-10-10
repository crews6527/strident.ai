"""End-to-end checks for an isolated, honest idle diagnostic."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class IdleDiagnosticTests(unittest.TestCase):
    def probe(self, extra_startup=""):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            personal = root / "personal" / "PromptCopyStudioAgent"
            personal.mkdir(parents=True)
            settings = personal / "config.json"
            settings.write_bytes(b"invalid private config must remain untouched")
            database = personal / "studio.sqlite3"
            database.write_bytes(b"private database bytes")
            output = root / "result.json"
            code = extra_startup + "\nimport verify_idle\nsys.argv = ['verify_idle.py', '--seconds', '5', '--output', sys.argv[1]]\nraise SystemExit(verify_idle.main())\n"
            process = subprocess.run([sys.executable, "-c", "import sys\n" + code, str(output)],
                cwd=Path(__file__).resolve().parent.parent,
                env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "LOCALAPPDATA": str(root / "personal")},
                capture_output=True, text=True, timeout=30)
            self.assertTrue(output.is_file(), process.stdout + process.stderr)
            self.assertEqual(settings.read_bytes(), b"invalid private config must remain untouched")
            self.assertEqual(database.read_bytes(), b"private database bytes")
            return process, json.loads(output.read_text())

    def test_idle_sample_uses_temporary_data_and_measured_request_count(self):
        process, result = self.probe()
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertTrue(result["ok"])
        self.assertTrue(result["data_isolated"])
        self.assertEqual(result["tasks_submitted"], 0)
        self.assertEqual(result["ollama_requests_attempted"], 0)
        self.assertNotIn("microphone_initialized", result)

    def test_attempted_startup_inference_is_blocked_counted_and_fails_check(self):
        process, result = self.probe('''
from pcs_agent.ui import ConsoleWindow
from pcs_agent.provider import Ollama
original_init = ConsoleWindow.__init__
def injected_startup(self, config):
    original_init(self, config)
    try:
        Ollama(config)._open('/api/chat', {'model': 'not-installed'})
    except RuntimeError:
        pass
ConsoleWindow.__init__ = injected_startup
''')
        self.assertEqual(process.returncode, 1, process.stdout + process.stderr)
        self.assertFalse(result["ok"])
        self.assertEqual(result["ollama_requests_attempted"], 1)
        self.assertEqual(result["inference_requests_attempted"], 1)


if __name__ == "__main__":
    unittest.main()
