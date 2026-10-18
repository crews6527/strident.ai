import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import guard_strident as guard


class LaunchGuardTests(unittest.TestCase):
    def test_clean_environment_removes_only_conflicts_without_mutating_parent(self):
        env = {'PYTHONPATH': 'bad', 'PythonHome': 'bad', 'QT_PLUGIN_PATH': 'other-app',
               'LOCALAPPDATA': 'private', 'PATH': 'system', 'OLLAMA_MODELS': 'models'}
        original = dict(env)
        result = guard.clean_environment(env)
        self.assertEqual(result, {k: env[k] for k in ('LOCALAPPDATA', 'PATH', 'OLLAMA_MODELS')})
        self.assertEqual(env, original)

    def fixture(self, root):
        paths = ['main.py', 'guard_strident.py', 'requirements.txt', 'pcs_agent/runtime.py', 'pcs_agent/ui.py']
        for name in paths:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('# verified\n')
        (root / 'SHA256SUMS.txt').write_text(''.join(
            hashlib.sha256((root / p).read_bytes()).hexdigest() + '  ' + p + '\n' for p in paths))
        return paths

    def test_integrity_reports_changed_missing_and_extra_modules(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            files = self.fixture(root)
            self.assertEqual(guard.check_integrity(root), len(files))
            (root / 'pcs_agent/runtime.py').write_text('changed')
            with self.assertRaisesRegex(RuntimeError, 'changed application file'): guard.check_integrity(root)
            self.fixture(root)
            (root / 'main.py').unlink()
            with self.assertRaisesRegex(RuntimeError, 'Missing or changed'): guard.check_integrity(root)
            self.fixture(root)
            (root / 'json.py').write_text('raise RuntimeError("foreign import")')
            with self.assertRaisesRegex(RuntimeError, 'Unexpected Python file'): guard.check_integrity(root)

    def test_manifest_cannot_read_outside_package(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('../private.txt', '/private.txt', 'C:/private.txt', 'pcs_agent/../../private.txt'):
                (root / 'SHA256SUMS.txt').write_text('0' * 64 + '  ' + name)
                with self.subTest(name=name), self.assertRaises(ValueError): guard.check_integrity(root)

    def test_dependency_drift_stops_launch(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'requirements.txt').write_text('psutil==7.2.2\n')
            with patch('guard_strident.metadata.version', return_value='0.0.1'):
                with self.assertRaisesRegex(RuntimeError, 'Dependency changed'): guard.check_dependencies(root)

    def test_isolated_preflight_ignores_global_pythonpath(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'json.py').write_text('raise RuntimeError("foreign PYTHONPATH executed")')
            result = subprocess.run([sys.executable, '-I', str(Path(guard.__file__).resolve()), '--check'],
                                    env={**os.environ, 'PYTHONPATH': folder, 'LOCALAPPDATA': folder},
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('No model or task was run', result.stdout)
            self.assertTrue(list((root / 'PromptCopyStudioAgent/startup-logs').glob('*.log')))
