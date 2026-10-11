import json
import os
import tempfile
import unittest
import subprocess
import queue
import sys
import time
from pathlib import Path
from unittest.mock import Mock, patch
from pcs_agent.config import validate
from pcs_agent.coding import (command_parts, validate_files, project_dir, latest_files,
                              save_revision, sandbox_status, sandbox_tests,
                              cleanup_container, coding_task, docker_env, SUPERVISOR)
from pcs_agent.runtime import execute, Controller

FILES = {'main.py': 'def add(a, b): return a + b\n',
         'tests/test_main.py': 'import unittest\nfrom main import add\nclass TestAdd(unittest.TestCase):\n def test_sum(self): self.assertEqual(add(2, 3), 5)\n'}
IMAGE_ID = 'sha256:' + 'a' * 64
CONTAINER = 'strident-code-12345678'


def coding_wait_worker(pipe, command, config, attachment, history):
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    pipe.send({'kind':'tool','name':'coding_write','result':{'ok':True,'summary':'Fixture revision saved','pid':child.pid,'container':config['_coding_container']}})
    time.sleep(30)


class CodingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = validate({'workspace': self.temp.name, 'data_dir': self.temp.name,
                                'model': 'coder:2b', 'num_predict': 2048, 'num_ctx': 8192})
        self.metrics = {'model_turns': 0}
        self.events = []

    def tearDown(self):
        self.temp.cleanup()

    def test_commands_preserve_entire_request_and_reject_extra_test_actions(self):
        self.assertEqual(command_parts('/code demo write X\nthen debug it'), ('code', 'demo', 'write X\nthen debug it'))
        self.assertEqual(command_parts('/testcode demo'), ('testcode', 'demo', ''))
        self.assertIsNone(command_parts('write a poem about code'))
        for text in ('/code ../demo do it', '/code demo', '/testcode demo then open browser'):
            with self.subTest(text=text), self.assertRaises(ValueError): command_parts(text)

    def test_paths_types_collisions_and_limits(self):
        self.assertEqual(validate_files(FILES), FILES)
        for path in ('../escape.py', '/escape.py', 'C:/escape.py', 'x\\y.py', '.env',
                     'a/../b.py', 'a//b.py', 'NUL.py', 'tests/COM1.py', 'run.cmd', 'A./x.py'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate_files({**FILES, path: 'x'})
        for files in ({'main.py': 'x'}, {**FILES, 'MAIN.py': 'x'},
                      {**FILES, 'large.txt': 'x' * 64001},
                      {**FILES, 'main.py/child.py': 'x'}, {**FILES, 'x.py': 1}):
            with self.assertRaises(ValueError): validate_files(files)

    def test_revisions_keep_old_source_and_latest_retests_current(self):
        first = save_revision(self.config, 'demo', FILES)
        newer = {**FILES, 'main.py': 'def add(a,b): return a-b\n'}
        second = save_revision(self.config, 'demo', newer)
        self.assertNotEqual(first, second)
        self.assertEqual((first/'source/main.py').read_text(), FILES['main.py'])
        self.assertEqual(latest_files(self.config, 'demo'), newer)
        self.assertEqual(list(Path(self.temp.name).glob('*.py')), [])

    @unittest.skipUnless(hasattr(os, 'symlink'), 'Symlinks unavailable')
    def test_symlink_folders_and_sources_never_read_or_written(self):
        outer = Path(self.temp.name)/'outside'; outer.mkdir()
        try: (Path(self.temp.name)/'Coding').symlink_to(outer, target_is_directory=True)
        except OSError as exc: self.skipTest(str(exc))
        with self.assertRaises(ValueError): project_dir(self.config, 'demo')
        (Path(self.temp.name)/'Coding').unlink()
        revision = save_revision(self.config, 'demo', FILES)
        (revision/'source/main.py').unlink()
        (revision/'source/main.py').symlink_to(outer/'secret.py')
        with self.assertRaises(ValueError): latest_files(self.config, 'demo')

    def test_missing_docker_fails_closed_without_model_or_source(self):
        with patch('pcs_agent.coding.shutil.which', return_value=None), patch('pcs_agent.coding.Ollama') as model:
            result = execute('/code demo write an adder', self.config, '', [], self.events.append)
        self.assertEqual(result['status'], 'needs_attention')
        self.assertIn('Docker is missing', result['summary'])
        model.assert_not_called()
        self.assertFalse((Path(self.temp.name)/'Coding').exists())

    def test_engine_and_image_must_be_verified(self):
        for response in (subprocess.CompletedProcess([], 1, '', 'error'), subprocess.CompletedProcess([], 0, 'windows\n', '')):
            with patch('pcs_agent.coding.docker_call', return_value=response), self.assertRaises(RuntimeError): sandbox_status()
        with patch('pcs_agent.coding.docker_call', side_effect=[subprocess.CompletedProcess([],0,'linux\n',''), subprocess.CompletedProcess([],1,'','missing')]), self.assertRaises(RuntimeError): sandbox_status()
        with patch('pcs_agent.coding.docker_call', side_effect=[subprocess.CompletedProcess([],0,'linux\n',''), subprocess.CompletedProcess([],0,IMAGE_ID+'\n','')]):
            self.assertEqual(sandbox_status()['image_id'], IMAGE_ID)

    def test_container_constraints_no_host_mounts_and_cleanup(self):
        report = {'exit_code': 0, 'output': 'Ran 1 test in 0.001s\n\nOK\n', 'timed_out': False, 'truncated': False}
        with patch('pcs_agent.coding.docker_call', side_effect=[subprocess.CompletedProcess([],0,'id',''), subprocess.CompletedProcess([],0,json.dumps(report),''), subprocess.CompletedProcess([],0,'removed','')]) as call:
            result = sandbox_tests(FILES, IMAGE_ID, CONTAINER)
        self.assertTrue(result['ok'])
        create = call.call_args_list[0].args[0]
        for value in ('--read-only', '--network', 'none', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--memory', '256m', '--memory-swap', '--cpus', '--pids-limit', '--user', '65534:65534', '--tmpfs', '--log-driver', 'none', IMAGE_ID):
            self.assertIn(value, create)
        self.assertFalse(any(x in create for x in ('--privileged', '--volume', '--mount', '-v', '--publish')))
        self.assertEqual(json.loads(call.call_args_list[1].kwargs['input'])['files'], FILES)
        self.assertEqual(call.call_args_list[-1].args[0], ['rm', '--force', CONTAINER])

    def test_empty_suite_failed_tests_timeout_and_bad_report_are_not_success(self):
        for code, output, timed in ((0, 'Ran 0 tests in 0s\nOK', False), (0, 'Ran 1 test in 0s\nOK (skipped=1)', False), (1, 'Ran 1 test in 0s\nFAILED', False), (124, 'partial', True)):
            report = {'exit_code': code, 'output': output, 'timed_out': timed}
            with patch('pcs_agent.coding.docker_call', side_effect=[subprocess.CompletedProcess([],0,'id',''), subprocess.CompletedProcess([],code,json.dumps(report),''), subprocess.CompletedProcess([],0,'','')]):
                self.assertFalse(sandbox_tests(FILES, IMAGE_ID, CONTAINER)['ok'])
        for effect in (subprocess.TimeoutExpired('docker',30), subprocess.CompletedProcess([],1,'bad JSON','failed')):
            with patch('pcs_agent.coding.docker_call', side_effect=[subprocess.CompletedProcess([],0,'id',''), effect, subprocess.CompletedProcess([],0,'','')]) as call:
                with self.assertRaises((RuntimeError, subprocess.TimeoutExpired)): sandbox_tests(FILES, IMAGE_ID, CONTAINER)
                self.assertEqual(call.call_args_list[-1].args[0], ['rm', '--force', CONTAINER])

    def test_cleanup_failure_is_visible_and_bad_names_cannot_be_arguments(self):
        with patch('pcs_agent.coding.docker_call', return_value=subprocess.CompletedProcess([],1,'','permission denied')), self.assertRaises(RuntimeError): cleanup_container(CONTAINER)
        with patch('pcs_agent.coding.docker_call') as call, self.assertRaises(ValueError): cleanup_container('--all')
        call.assert_not_called()
        with patch.dict(os.environ, {'DOCKER_HOST':'tcp://remote:1234', 'DOCKER_CONTEXT':'unsafe'}):
            self.assertNotIn('DOCKER_HOST', docker_env())
            self.assertNotIn('DOCKER_CONTEXT', docker_env())

    def fake_model(self, replies):
        client = Mock()
        client.inspect.return_value = {'models': [{'name':'coder:2b'}]}
        client.json.return_value = {'capabilities': [], 'thinking': {'values':[False]}}
        client.chat.side_effect = replies
        return client

    def test_failure_then_repair_keeps_both_revisions_and_logs(self):
        bad = {**FILES, 'main.py': 'def add(a,b): return a-b\n'}
        client = self.fake_model([{'content':json.dumps({'files':bad})}, {'content':json.dumps({'files':FILES})}])
        failed = {'ok': False,'summary':'Tests failed','output':'AssertionError: -1 != 5'}
        passed = {'ok': True,'summary':'Tests passed','output':'Ran 1 test in 0.01s\nOK'}
        with patch('pcs_agent.coding.sandbox_status', return_value={'ok':True,'summary':'Available','image_id':IMAGE_ID}), patch('pcs_agent.coding.Ollama',return_value=client), patch('pcs_agent.coding.sandbox_tests',side_effect=[failed,passed]):
            result = coding_task('code','demo','Write an adder',self.config,self.events.append,self.metrics)
        self.assertEqual(result['status'],'complete')
        self.assertEqual(self.metrics['model_turns'],2)
        self.assertIn('AssertionError',client.chat.call_args_list[1].args[0][-1]['content'])
        revisions = list(project_dir(self.config,'demo').iterdir())
        self.assertEqual(len(revisions),2)
        self.assertTrue(all((p/'test-report.json').exists() for p in revisions))
        self.assertEqual(latest_files(self.config,'demo'),FILES)
        self.assertTrue(any(e.get('name')=='sandbox_tests' and not e['result']['ok'] for e in self.events))

    def test_invalid_source_never_saved_and_repair_loop_is_bounded(self):
        client=self.fake_model([{'content':'not JSON'}]*3)
        with patch('pcs_agent.coding.sandbox_status', return_value={'ok':True,'summary':'Available','image_id':IMAGE_ID}), patch('pcs_agent.coding.Ollama',return_value=client), patch('pcs_agent.coding.sandbox_tests') as test:
            result=coding_task('code','demo','Write an adder',self.config,self.events.append,self.metrics)
        self.assertEqual(result['status'],'needs_attention')
        self.assertEqual(client.chat.call_count,3)
        test.assert_not_called()
        self.assertFalse((Path(self.temp.name)/'Coding').exists())

    def test_truncated_model_response_cannot_be_marked_complete(self):
        client=self.fake_model([{'content':json.dumps({'files':FILES}),'output_truncated':True}])
        with patch('pcs_agent.coding.sandbox_status', return_value={'ok':True,'summary':'Available','image_id':IMAGE_ID}), patch('pcs_agent.coding.Ollama',return_value=client):
            result=coding_task('code','demo','Write an adder',self.config,self.events.append,self.metrics)
        self.assertEqual(result['status'],'needs_attention')
        self.assertIn('token limit',result['summary'])
        self.assertFalse((Path(self.temp.name)/'Coding').exists())

    def test_retest_uses_saved_source_without_model_inference(self):
        save_revision(self.config,'demo',FILES)
        with patch('pcs_agent.coding.sandbox_status', return_value={'ok':True,'summary':'Available','image_id':IMAGE_ID}), patch('pcs_agent.coding.Ollama') as model, patch('pcs_agent.coding.sandbox_tests',return_value={'ok':True,'summary':'Passed'}) as test:
            result=coding_task('testcode','demo','',self.config,self.events.append,self.metrics)
        self.assertEqual(result['status'],'complete'); model.assert_not_called()
        self.assertEqual(test.call_args.args[0],FILES)
        self.assertEqual(len(list(project_dir(self.config,'demo').glob('*/test-report.json'))),1)

    def test_supervisor_syntax_and_independent_deadline(self):
        compile(SUPERVISOR,'container-supervisor','exec')
        self.assertIn('child.wait(timeout=20)',SUPERVISOR)
        self.assertIn('12000-len(output)',SUPERVISOR)
        self.assertIn('sys.exit(code',SUPERVISOR)

    def run_trusted_supervisor_fixture(self, files, *, short_timeout=False):
        # These are fixed test fixtures, not user/model-generated programs.
        # This exercises the supervisor protocol, not container isolation.
        with tempfile.TemporaryDirectory() as folder:
            program=SUPERVISOR.replace("pathlib.Path('/tmp/project')", 'pathlib.Path('+repr(str(Path(folder)/'project'))+')')
            if short_timeout: program=program.replace('child.wait(timeout=20)','child.wait(timeout=.2)')
            result=subprocess.run([sys.executable,'-I','-c',program],input=json.dumps({'files':files}),capture_output=True,text=True,timeout=5)
            return result.returncode,json.loads(result.stdout)

    def test_real_supervisor_protocol_pass_failure_bounded_output_and_deadline(self):
        code,result=self.run_trusted_supervisor_fixture(FILES)
        self.assertEqual(code,0); self.assertIn('Ran 1 test',result['output'])
        bad={**FILES,'main.py':'def add(a,b): return a-b\n'}
        code,result=self.run_trusted_supervisor_fixture(bad)
        self.assertNotEqual(code,0); self.assertIn('AssertionError',result['output'])
        noisy={**FILES,'main.py':"print('x'*30000)\ndef add(a,b): return a+b\n"}
        code,result=self.run_trusted_supervisor_fixture(noisy)
        self.assertEqual(code,0); self.assertTrue(result['truncated'])
        self.assertLessEqual(len(result['output'].encode()),12000)
        slow={**FILES,'main.py':'import time\ntime.sleep(30)\ndef add(a,b): return a+b\n'}
        code,result=self.run_trusted_supervisor_fixture(slow,short_timeout=True)
        self.assertEqual(code,124); self.assertTrue(result['timed_out'])

    def test_controller_cancel_cleans_container_owned_child_and_keeps_evidence(self):
        import psutil
        events=queue.Queue()
        with patch('pcs_agent.coding.cleanup_container') as cleanup:
            controller=Controller(events.put,worker=coding_wait_worker)
            try:
                task=controller.submit('/code demo write tests',self.config)
                deadline=time.monotonic()+5
                observed=None
                while time.monotonic()<deadline:
                    event=events.get(timeout=2)
                    if event['kind']=='tool':
                        observed=event['result']; controller.cancel_task(task); break
                self.assertIsNotNone(observed)
                while time.monotonic()<deadline:
                    event=events.get(timeout=2)
                    if event['kind']=='result': break
                self.assertEqual(event['status'],'cancelled')
                self.assertEqual(event['evidence'][0]['pid'],observed['pid'])
                while controller.active and time.monotonic()<deadline: time.sleep(.02)
                cleanup.assert_called_with('strident-code-'+task)
                if psutil.pid_exists(observed['pid']):
                    self.assertEqual(psutil.Process(observed['pid']).status(), psutil.STATUS_ZOMBIE)
            finally: controller.close()


class CodingUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PyQt6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_page_queues_explicit_budget_without_startup_docker_or_inference(self):
        from pcs_agent.ui import ConsoleWindow
        with patch('pcs_agent.coding.docker_call') as docker, patch('pcs_agent.coding.Ollama') as model:
            window=ConsoleWindow(validate({}),preview=True)
            window.navigate('Coding')
            self.assertEqual(window.pages.currentIndex(),7)
            docker.assert_not_called(); model.assert_not_called()
            with patch.object(window,'submit') as submit:
                window.coding_page.project.setText('demo')
                window.coding_page.request.setPlainText('Write an adder and test it')
                window.coding_page.generate()
                self.assertEqual(submit.call_args.args[0],'/code demo Write an adder and test it')
                self.assertEqual(submit.call_args.kwargs['config']['task_timeout'],180)
                self.assertEqual(window.config['task_timeout'],60)
            window.close()
