import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import queue
import tempfile
import time
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
from pcs_agent.compliance import request_url
from pcs_agent.config import validate
from pcs_agent.runtime import Controller, execute, worker_entry
from pcs_agent.storage import State
from PyQt6.QtWidgets import QApplication
from pcs_agent.ui import ConsoleWindow


REQUEST = (Path(__file__).parent / 'fixtures/compliance_request.txt').read_text(encoding='utf-8')
HTML = '<html><head><title>Test storefront</title><meta name="description" content="Test digital downloads"><meta name="viewport" content="width=device-width"></head><body><h1>Downloads</h1><p>A synthetic storefront for bounded inspection tests only. No actual customer records or paid delivery.</p></body></html>'


def fixture_worker(pipe, command, config, attachment, history):
    # Patch inside the spawned child. The task still runs the real dispatcher,
    # local catalog, PDF audit, report writer and Controller/UI event transport.
    with patch('pcs_agent.website.fetch', return_value=(HTML, 'https://example.com', 'text/html', False)), patch('pcs_agent.runtime.Ollama', side_effect=AssertionError('Model must not be initialized')):
        worker_entry(pipe, command, config, attachment, history)


class ComplianceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = validate({'data_dir': str(self.root / 'data'), 'workspace': str(self.root / 'workspace'), 'model': 'unavailable:2b'})

    def tearDown(self):
        self.temp.cleanup()

    def add_product(self, product_id='test', missing=False):
        asset = self.root / (product_id + '.pdf')
        if not missing:
            writer = PdfWriter()
            writer.add_blank_page(width=200, height=200)
            writer.write(asset)
        State(self.config['data_dir']).upsert_product({'id': product_id, 'title': 'Synthetic product', 'asset': str(asset), 'checkout_url': 'https://example.com/buy', 'expected_pages': 1})

    def run_request(self, fetch_result=(HTML, 'https://example.com', 'text/html', False), command=REQUEST):
        events = []
        with patch('pcs_agent.website.fetch', return_value=fetch_result) as fetch, patch('pcs_agent.runtime.Ollama') as model:
            result = execute(command, self.config, '', [], events.append)
        model.assert_not_called()
        self.assertEqual(fetch.call_count, 1)
        self.assertFalse(fetch.call_args.kwargs['browser_cookie'])
        return result, events

    def test_full_request_bypasses_unavailable_model_and_preserves_all_items(self):
        result, events = self.run_request()
        self.assertEqual(result['metrics']['model_turns'], 0)
        self.assertEqual(result['metrics']['route'], 'compliance checks')
        self.assertEqual(result['status'], 'needs_attention')
        self.assertNotIn('Ollama /api/chat', result['reply'])
        files = result['evidence'][-1]['files']
        report = json.loads(Path(files[1]).read_text())
        self.assertEqual(report['original_request'], REQUEST)
        for line in REQUEST.splitlines():
            if line.strip(): self.assertIn(line, Path(files[0]).read_text())
        self.assertFalse(report['compliance_certified'])
        self.assertFalse(report['published'])
        self.assertEqual(result['history'][0]['content'], REQUEST)
        self.assertEqual(events[0]['kind'], 'log')

    def test_explicit_target_wins_over_settings_and_reference_urls(self):
        self.assertEqual(request_url(REQUEST, 'https://other.example.com'), 'https://promptcopystudio.42web.io')
        text = 'Please audit my website https://example.com/shop. Privacy, CSP, HSTS. Reference https://reference.example.com'
        self.assertEqual(request_url(text, 'https://other.example.com'), 'https://example.com/shop')

    def test_configured_url_used_only_when_no_explicit_target(self):
        self.assertEqual(request_url('Check my website for privacy, RLS and CSP.', 'https://example.com'), 'https://example.com')

    def test_explicit_command_and_natural_variants_bypass_model(self):
        for command in ('Check compliance', '/compliance', 'Run compliance check', "I'm worried so please check my website for compliance.", 'Optimize my website SEO and product descriptions.', 'Check my website and make it pass Google and Apple store compliance.'):
            with self.subTest(command=command):
                result, _ = self.run_request(command=command)
                self.assertEqual(result['metrics']['model_turns'], 0)
        self.assertEqual(request_url('/compliance https://example.com', self.config['store_url']), 'https://example.com')

    def test_runtime_identity_and_route_are_visible_before_model(self):
        _, events = self.run_request()
        self.assertIn('Strident.AI 3.3.1', events[0]['text'])
        self.assertIn('Source folder:', events[0]['text'])
        self.assertTrue(any('Route: compliance checks' in e.get('text', '') for e in events))

    def test_explanations_quoted_examples_and_negated_requests_do_not_visit(self):
        for command in ('Explain this checklist: ' + REQUEST, 'Write a draft: ' + REQUEST, 'Remember example: ' + REQUEST, 'Do not check my website for privacy, RLS or CSP.', 'Explain "Please check my website for privacy, RLS and CSP"', '"Please check my website for privacy, RLS and CSP"', 'Check my website and rewrite everything'):
            with self.subTest(command=command): self.assertIsNone(request_url(command, self.config['store_url']))

    def test_local_addresses_cannot_be_inspected_as_public_websites(self):
        for target in ('localhost.local', 'http://127.0.0.1:8766', 'http://[::1]:8766', 'https://user:secret@example.com'):
            with self.subTest(target=target), self.assertRaises(ValueError):
                request_url(f'Check my website {target} for privacy, RLS and CSP.', self.config['store_url'])

    def test_blocked_website_does_not_skip_product_audit_or_lose_blocker(self):
        self.add_product()
        blocked = ('<html><p>Verify you are human</p></html>', 'https://example.com', 'text/html', False)
        result, _ = self.run_request(blocked)
        self.assertFalse(result['evidence'][0]['ok'])
        product = next(r for r in result['evidence'] if r['tool'] == 'store_audit')
        self.assertEqual(product['audit']['pages'], 1)
        self.assertIn('access challenge', result['reply'])

    def test_one_missing_product_does_not_stop_remaining_files(self):
        self.add_product('missing', missing=True)
        self.add_product('valid')
        result, _ = self.run_request()
        products = [r for r in result['evidence'] if r['tool'] == 'store_audit']
        self.assertEqual(len(products), 2)
        self.assertEqual(sum(p['ok'] for p in products), 1)

    def test_product_batches_are_bounded_and_deferred_ids_are_visible(self):
        for i in range(12): self.add_product(f'p{i:02}')
        result, _ = self.run_request()
        self.assertEqual(len([r for r in result['evidence'] if r['tool'] == 'store_audit']), 10)
        self.assertIn('Audit product p10', result['reply'])
        self.assertIn('Audit product p11', result['reply'])

    def test_no_catalog_has_actionable_message_and_no_completion_claim(self):
        result, _ = self.run_request()
        self.assertIn('No registered product files', result['reply'])
        self.assertIn('full compliance request remains unfinished', result['reply'])

    def test_report_write_failure_keeps_prior_evidence(self):
        with patch('pcs_agent.compliance.save_report', side_effect=PermissionError('Read-only workspace')):
            result, _ = self.run_request()
        self.assertFalse(result['evidence'][-1]['ok'])
        self.assertIn('Read-only workspace', result['reply'])
        self.assertTrue(result['evidence'][0]['ok'])

    def test_existing_report_symlink_cannot_write_outside_workspace(self):
        outside = self.root / 'outside'
        outside.mkdir()
        workspace = Path(self.config['workspace'])
        workspace.mkdir()
        (workspace / 'website_reports').symlink_to(outside, target_is_directory=True)
        result, _ = self.run_request()
        self.assertFalse(result['evidence'][-1]['ok'])
        self.assertEqual(list(outside.iterdir()), [])

    def test_native_ui_spawned_worker_pdf_report_and_saved_evidence(self):
        self.add_product()
        app = QApplication.instance() or QApplication([])
        window = ConsoleWindow(self.config, preview=True)
        window.preview = False
        window.controller = Controller(window.bus.event.emit, worker=fixture_worker, storage=State(self.config['data_dir']))
        try:
            window.submit(REQUEST)
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                app.processEvents()
                if window.records and next(iter(window.records.values()))['status'] == 'needs_attention': break
                time.sleep(.01)
            record = next(iter(window.records.values()))
            self.assertEqual(record['status'], 'needs_attention')
            self.assertEqual(record['metrics']['model_turns'], 0)
            self.assertIn('Available checks finished', window.results.toPlainText())
            self.assertIn('No model inference', window.console.toPlainText())
            self.assertIn('Strident.AI 3.3.1', window.windowTitle())
            self.assertTrue(any(r.get('audit', {}).get('pages') == 1 for r in record['evidence']))
            saved = State(self.config['data_dir']).tool_result({'compliance_report'})
            self.assertTrue(Path(saved[1]['files'][1]).is_file())
        finally:
            window.close()
            app.processEvents()


if __name__ == '__main__': unittest.main()
