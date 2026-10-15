import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from apply_update import install, manifest_files, validate_target
from diagnose_install import installation_report, collect_model_evidence
from pcs_agent.config import validate


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.target = self.root / 'target'
        self.source.mkdir(); self.target.mkdir()
        self.files = {'main.py': 'new main', 'Launch-Strident.cmd': 'launcher', 'pcs_agent/runtime.py': 'new runtime', 'pcs_agent/compliance.py': 'new checker', 'requirements.txt': 'pins', 'verify_app.py': 'checks'}
        for name, content in self.files.items():
            file = self.source / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(content)
        for name in ('main.py', 'Launch-Strident.cmd', 'pcs_agent/runtime.py'):
            file = self.target / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text('old '+name)
        from apply_update import interpreter
        python = interpreter(self.target)
        python.parent.mkdir(parents=True)
        python.write_text('synthetic interpreter')
        self.manifest()

    def manifest(self):
        (self.source / 'SHA256SUMS.txt').write_text(''.join(hashlib.sha256((self.source/n).read_bytes()).hexdigest()+'  '+n+'\n' for n in self.files))

    def tearDown(self): self.temp.cleanup()

    def test_package_hashes_and_target_validation(self):
        files=manifest_files(self.source)
        self.assertEqual(validate_target(self.target, files, self.source), self.target)
        self.assertIn('SHA256SUMS.txt', files)
        (self.source/'main.py').write_text('corrupted')
        with self.assertRaisesRegex(ValueError, 'checksum'): manifest_files(self.source)

    def test_update_in_place_preserves_settings_database_and_original_backup(self):
        (self.target/'config.json').write_bytes(b'private settings')
        (self.target/'studio.sqlite3').write_bytes(b'private database')
        verifier=Mock()
        backup=install(self.source,self.target,manifest_files(self.source),verifier)
        verifier.assert_called_once_with(self.target)
        self.assertEqual((self.target/'main.py').read_text(),'new main')
        self.assertEqual((backup/'main.py').read_text(),'old main.py')
        self.assertEqual((self.target/'config.json').read_bytes(),b'private settings')
        self.assertEqual((self.target/'studio.sqlite3').read_bytes(),b'private database')

    def test_verification_failure_rolls_back_old_files_and_removes_only_added_source(self):
        original=(self.target/'main.py').read_bytes()
        with self.assertRaises(RuntimeError):
            install(self.source,self.target,manifest_files(self.source),Mock(side_effect=RuntimeError('failed check')))
        self.assertEqual((self.target/'main.py').read_bytes(),original)
        self.assertFalse((self.target/'pcs_agent/compliance.py').exists())
        self.assertTrue(list((self.target/'backups').glob('*/restore-index.json')))

    def test_new_source_folder_cannot_be_mistaken_for_existing_installation(self):
        with self.assertRaisesRegex(ValueError,'extracted update'): validate_target(self.source,self.files,self.source)

    def test_private_or_external_paths_cannot_be_in_the_update(self):
        for relative in ('config.json','.env','backups/private.txt','../escape.py'):
            with self.subTest(relative=relative):
                (self.source/'SHA256SUMS.txt').write_text('a'*64+'  '+relative+'\n')
                with self.assertRaises(ValueError): manifest_files(self.source)

    def test_target_source_symlink_and_backup_symlink_cannot_escape(self):
        outside=self.root/'outside'; outside.mkdir()
        (self.target/'pcs_agent/runtime.py').unlink()
        (self.target/'pcs_agent/runtime.py').symlink_to(outside/'runtime.py')
        with self.assertRaises(ValueError):validate_target(self.target,self.files,self.source)
        (self.target/'backups').symlink_to(outside,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'outside'):install(self.source,self.target,self.files,Mock())
        self.assertEqual(list(outside.iterdir()),[])

    def test_diagnostic_identifies_actual_local_build_and_explicit_route_without_inference(self):
        config=validate({'model':'qwen3.5:2b'})
        with patch('diagnose_install.Ollama') as model:
            result=installation_report(command='Check compliance',config=config)
        model.assert_not_called()
        self.assertEqual(result['version'],'3.3.1')
        self.assertEqual(result['route'],'compliance checks')
        self.assertFalse(result['will_call_ollama'])
        self.assertIn('no automatic GitHub sync',result['source_origin'])
        self.assertNotIn('command',result)
        self.assertEqual(installation_report(command='Hello',config=config)['route'],'model')

    def test_model_diagnostic_reports_failure_without_changing_configuration(self):
        config=validate({'model':'qwen3.5:2b'})
        original=dict(config)
        client=Mock()
        client.inspect.return_value={'version':'test','models':[]}
        client.json.return_value={'models':[{'name':'qwen3.5:2b','size':1,'size_vram':0}]}
        with patch('diagnose_install.Ollama',return_value=client), patch('diagnose_ollama.run_check',return_value={'ok':False,'error':'Response timed out'}) as probe:
            result=collect_model_evidence(config)
        self.assertFalse(result['model_probe']['ok'])
        self.assertEqual(config,original)
        self.assertEqual(probe.call_args.args[0]['model'],'qwen3.5:2b')


if __name__ == '__main__': unittest.main()
