import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from pcs_agent.instance import InstanceLock

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('startup_probe', ROOT / 'diagnostics/check_startup.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class StartupProbeTests(unittest.TestCase):
    def test_real_probe_distinguishes_config_failure_lock_conflict_and_success(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'LOCALAPPDATA': folder}):
            root = Path(folder)
            config_path = root / 'PromptCopyStudioAgent/config.json'
            config_path.parent.mkdir()
            config_path.write_text('{broken json', encoding='utf-8')
            result = probe.probe(ROOT, sys.executable)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('JSONDecodeError', result.stderr)
            self.assertNotIn('STEP 3', result.stdout)
            self.assertEqual(config_path.read_text(), '{broken json')
            cfg = {'data_dir': str(root / 'data'), 'workspace': str(root / 'workspace')}
            config_path.write_text(json.dumps(cfg), encoding='utf-8')
            original = config_path.read_bytes()
            lock = InstanceLock(cfg['data_dir'])
            try:
                result = probe.probe(ROOT, sys.executable)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Strident is already running', result.stderr)
                self.assertIn('PASS: Saved settings loaded', result.stdout)
            finally:
                lock.close()
            result = probe.probe(ROOT, sys.executable)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('STARTUP CHECK PASSED', result.stdout)
            self.assertEqual(config_path.read_bytes(), original)
