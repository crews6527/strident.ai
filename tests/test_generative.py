import base64
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from pcs_agent.config import validate
from pcs_agent.runtime import execute
from pcs_agent.policy import CORE_POLICY
from pcs_agent.images import local_url, image_task, request


class CreativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = validate({'workspace': self.tmp.name, 'data_dir': self.tmp.name,
                                'model': 'test:2b', 'num_ctx': 8192, 'num_predict': 512})
        self.client = Mock()
        self.client.inspect.return_value = {'models': [{'name': 'test:2b'}]}
        self.client.json.return_value = {'thinking': {'values': [False]}}
        self.client.chat.side_effect = [{'content': text} for text in ['plan', 'draft', 'review', 'final']]
    def tearDown(self):
        self.tmp.cleanup()
    def run_task(self, text, config=None, attachment=''):
        with patch('pcs_agent.generative.Ollama', return_value=self.client):
            return execute(text, config or self.config, attachment, [], lambda e: None)
    def test_team_four_real_calls_with_policy_request_and_handoffs(self):
        result = self.run_task('/team Design a sales experiment using supplied evidence')
        self.assertEqual(result['reply'], 'final')
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['metrics']['model_turns'], 4)
        self.assertEqual([x['stage'] for x in result['evidence']], ['planner','creator','reviewer','editor'])
        for call in self.client.chat.call_args_list:
            self.assertIn(CORE_POLICY, call.args[0][0]['content'])
            self.assertEqual(call.args[0][-1]['content'], 'Design a sales experiment using supplied evidence')
            self.assertEqual(call.args[1], [])
        final_context = str(self.client.chat.call_args_list[-1].args[0])
        self.assertIn('review', final_context)
    def test_team_role_uses_orchestrator(self):
        self.assertEqual(self.run_task('/role team Write a story')['metrics']['model_turns'], 4)
    def test_create_preserves_full_configured_generation_budget(self):
        self.assertEqual(self.run_task('/create Write a website')['metrics']['model_turns'], 1)
        self.assertEqual(self.client.chat.call_count, 1)
    def test_failure_keeps_prior_work(self):
        self.client.chat.side_effect = [{'content': 'completed plan'}, RuntimeError('offline')]
        result = self.run_task('/team Write a report')
        self.assertEqual(result['status'], 'needs_attention')
        self.assertIn('completed plan', result['reply'])
        self.assertEqual(len(result['evidence']), 1)
    def test_truncation_stops_pipeline(self):
        self.client.chat.side_effect = [{'content': 'partial plan', 'output_truncated': True}]
        result = self.run_task('/team Write a report')
        self.assertEqual(result['status'], 'needs_attention')
        self.assertEqual(self.client.chat.call_count, 1)
    def test_tool_call_never_executes(self):
        self.client.chat.side_effect = [{'content': 'x', 'tool_calls': [{'function': {'name': 'open_app'}}]}]
        with patch('pcs_agent.runtime.ToolRunner') as runner:
            with self.assertRaises(RuntimeError):
                self.run_task('/create Write code')
            runner.assert_not_called()
    def test_member_team_has_no_host_attachment_access(self):
        with patch('pcs_agent.runtime.ToolRunner') as runner:
            result = self.run_task('/team Write a story', {**self.config, '_member_mode': True}, '/private/file')
            runner.assert_not_called()
        self.assertEqual(result['metrics']['model_turns'], 4)
    def test_member_image_is_denied_without_network(self):
        with patch('pcs_agent.images.request') as api:
            with self.assertRaises(PermissionError):
                self.run_task('/image a cat', {**self.config, '_member_mode': True})
            api.assert_not_called()
    def test_capabilities_works_without_model(self):
        result = self.run_task('/capabilities', {**self.config, 'model': ''})
        self.client.inspect.assert_not_called()
        self.assertIn('not neural-network training', result['reply'])
    def test_empty_request_is_rejected(self):
        with self.assertRaises(ValueError): self.run_task('/team')
        self.client.inspect.assert_not_called()
    def test_oversized_request_not_silently_truncated(self):
        with self.assertRaises(ValueError): self.run_task('/team ' + 'a' * 12000, {**self.config, 'num_ctx': 1024})
        self.client.chat.assert_not_called()
    def test_limited_handoff_reported(self):
        self.client.chat.side_effect = [{'content': 'a'*9000}, {'content':'draft'}, {'content':'review'}, {'content':'final'}]
        self.assertEqual(self.run_task('/team Write a report')['status'], 'needs_attention')


class ImageTests(unittest.TestCase):
    def test_urls_reject_remote_credentials_paths_and_bad_ports(self):
        for value in ['http://example.com', 'https://127.0.0.1', 'http://127.0.0.1.evil',
                      'http://127.0.0.1/a', 'http://u:p@127.0.0.1', 'http://127.0.0.1:bad']:
            with self.subTest(value=value), self.assertRaises(ValueError): local_url(value)
    def test_bad_image_never_saved(self):
        with tempfile.TemporaryDirectory() as folder:
            config=validate({'workspace':folder})
            with patch('pcs_agent.images.request', return_value={'images':[base64.b64encode(b'not png').decode()]}):
                with self.assertRaises(ValueError): image_task('/image cat', config, lambda e:None, {'tool_calls':0})
            self.assertEqual(list(Path(folder).rglob('*.png')), [])
    def test_local_http_api_status_and_file_result(self):
        png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9XcAAAAASUVORK5CYII=')
        received=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*a): pass
            def do_GET(self):
                self.send_response(200);self.end_headers();self.wfile.write(b'[{"title":"fixture model"}]')
            def do_POST(self):
                received.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                self.send_response(200);self.end_headers();self.wfile.write(json.dumps({'images':[base64.b64encode(png).decode()]}).encode())
        server=HTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as folder:
                cfg=validate({'workspace':folder,'image_url':f'http://127.0.0.1:{server.server_port}'})
                status=image_task('/image-status',cfg,lambda e:None,{'tool_calls':0})
                self.assertEqual(status['status'],'complete')
                result=image_task('/image a cat',cfg,lambda e:None,{'tool_calls':0})
                saved=Path(result['evidence'][0]['path'])
                self.assertEqual(saved.read_bytes(),png)
                self.assertEqual(received[0][0],'/sdapi/v1/txt2img')
                self.assertEqual(received[0][1]['prompt'],'a cat')
                self.assertEqual(received[0][1]['batch_size'],1)
        finally:
            server.shutdown();server.server_close();thread.join()
    def test_redirect_blocked(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*a): pass
            def do_GET(self):
                self.send_response(302);self.send_header('Location','http://example.com/');self.end_headers()
        server=HTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            cfg=validate({'image_url':f'http://127.0.0.1:{server.server_port}'})
            with self.assertRaisesRegex(ValueError,'redirects'):
                request(cfg,'/sdapi/v1/sd-models')
        finally:
            server.shutdown();server.server_close();thread.join()

if __name__=='__main__': unittest.main()
