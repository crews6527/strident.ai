import contextlib
import json
import multiprocessing
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock, patch
from pcs_agent.config import validate, load
from pcs_agent.provider import Ollama, nonthinking_value
from pcs_agent.runtime import execute
from pcs_agent.tools import direct_command
from diagnose_ollama import run_check


@contextlib.contextmanager
def server_for(*, header_delay=0, body_delay=0, reasoning_only=False):
    captured = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def send_json(self, value):
            raw = json.dumps(value).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        def do_GET(self):
            try:
                if self.path == "/api/version":
                    self.send_json({"version": "test-server"})
                else:
                    self.send_json({"models": [{"name": "qwen3.5:2b"}]})
            except (BrokenPipeError, ConnectionResetError):
                pass
        def do_POST(self):
            value = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            captured.append((self.path, value))
            try:
                if self.path == "/api/show":
                    self.send_json({"capabilities": ["tools", "thinking"], "thinking": {"values": [False, True], "default": True}})
                    return
                time.sleep(header_delay)
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.end_headers()
                first = {"message": {"thinking": "PRIVATE_REASONING_TEST"}, "done": False} if reasoning_only else {"message": {"content": "Hello "}, "done": False}
                self.wfile.write((json.dumps(first) + "\n").encode())
                self.wfile.flush()
                time.sleep(body_delay)
                last = {"message": {"content": "" if reasoning_only else "Tony"}, "done": True, "done_reason": "length" if reasoning_only else "stop"}
                self.wfile.write((json.dumps(last) + "\n").encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", captured
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def stuck_check(pipe, config):
    pipe.send({"kind": "log", "text": "model is still loading"})
    time.sleep(30)


class OllamaFixTests(unittest.TestCase):
    def test_single_web_addresses_route_directly_and_keep_full_url(self):
        self.assertEqual(direct_command("promptcopystudio.42web.io"),
                         ("read_web", {"url": "https://promptcopystudio.42web.io"}))
        url = "https://example.com/product?id=123&view=full"
        self.assertEqual(direct_command(url), ("read_web", {"url": url}))
        self.assertEqual(direct_command("example.com/product?id=123"),
                         ("read_web", {"url": "https://example.com/product?id=123"}))
        for text in ("example.com and draft a listing", "Review example.com", "qwen3.5:2b", "pcs_agent/tools.py"):
            with self.subTest(text=text):
                self.assertIsNone(direct_command(text))

    def test_bare_store_domain_reads_page_without_contacting_model(self):
        result = {"ok": True, "summary": "Retrieved page text.", "text": "Store page"}
        events = []
        with patch("pcs_agent.runtime.Ollama") as client, patch("pcs_agent.tools.ToolRunner.read_web", return_value=result) as read:
            actual = execute("promptcopystudio.42web.io", validate({}), "", [], events.append)
        client.assert_not_called()
        read.assert_called_once_with(url="https://promptcopystudio.42web.io")
        self.assertEqual(actual["status"], "complete")
        self.assertEqual(actual["evidence"][0]["tool"], "read_web")
        self.assertTrue(events[0]["stage"])

    def test_slow_model_start_uses_separate_wait_and_keeps_exact_tag(self):
        with server_for(header_delay=0.15) as (address, captured):
            config = validate({"ollama_url": address, "model": "qwen3.5:2b"})
            config.update(request_timeout=0.04, model_timeout=0.5)
            events = []
            message = Ollama(config).chat([{"role": "user", "content": "Hello"}], [], events.append, think=False)
            self.assertEqual(message["content"], "Hello Tony")
            self.assertEqual(captured[-1][1]["model"], "qwen3.5:2b")
            self.assertIs(captured[-1][1]["think"], False)
            self.assertTrue(events[0]["stage"])

    def test_first_response_timeout_identifies_chat_endpoint(self):
        with server_for(header_delay=0.15) as (address, captured):
            config = validate({"ollama_url": address, "model": "qwen3.5:2b"})
            config.update(model_timeout=0.03)
            with self.assertRaisesRegex(RuntimeError, r"/api/chat timed out.*waiting for the server"):
                Ollama(config).chat([], [], lambda e: None)

    def test_stream_timeout_identifies_output_wait_and_preserves_deltas(self):
        with server_for(body_delay=0.15) as (address, captured):
            config = validate({"ollama_url": address, "model": "qwen3.5:2b"})
            config.update(model_timeout=0.04)
            events = []
            with self.assertRaisesRegex(RuntimeError, r"/api/chat timed out.*waiting for model output"):
                Ollama(config).chat([], [], events.append)
            self.assertTrue(any(e.get("text") == "Hello " for e in events))

    def test_connection_refused_is_distinct_from_timeout(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        client = Ollama(validate({"ollama_url": f"http://127.0.0.1:{port}"}))
        with self.assertRaisesRegex(RuntimeError, r"Cannot connect to Ollama.*api/version"):
            client.inspect()

    def test_metadata_timeout_keeps_network_budget(self):
        client = Ollama(validate({"request_timeout": 5, "model_timeout": 45}))
        with patch("pcs_agent.provider.urllib.request.build_opener") as build:
            build.return_value.open.side_effect = TimeoutError()
            with self.assertRaisesRegex(RuntimeError, r"/api/show timed out after 5s"):
                client.json("/api/show", {"model": "qwen3.5:2b"})
            self.assertEqual(build.return_value.open.call_args.kwargs["timeout"], 5)

    def test_reasoning_only_completion_reports_token_limit_without_trace(self):
        with server_for(reasoning_only=True) as (address, captured):
            events = []
            with self.assertRaisesRegex(RuntimeError, "reasoning but no final answer.*token limit"):
                Ollama(validate({"ollama_url": address, "model": "qwen3.5:2b"})).chat([], [], events.append)
            self.assertNotIn("PRIVATE_REASONING_TEST", str(events))

    def test_thinking_controls_use_only_reported_boolean_false(self):
        self.assertIs(nonthinking_value({"thinking": {"values": [False, True]}}), False)
        for metadata in ({}, {"thinking": {"values": ["low", "high"]}}, {"thinking": {"values": [0, True]}}):
            self.assertIsNone(nonthinking_value(metadata))

    def test_capability_only_thinking_and_explicit_controls(self):
        self.assertIs(nonthinking_value({"capabilities": ["completion", "thinking"]}), False)
        self.assertIsNone(nonthinking_value({"capabilities": ["thinking"], "thinking": {"values": ["low", "high"]}}))

    def test_model_display_labels_are_rejected_before_request(self):
        with self.assertRaisesRegex(ValueError, "file-size label"):
            validate({"model": "qwen3.5:2b · 2.56 GB"})

    def test_disconnect_has_actionable_error(self):
        import http.client
        client = Ollama(validate({"model": "qwen3.5:2b"}))
        with patch("pcs_agent.provider.urllib.request.build_opener") as build:
            build.return_value.open.side_effect = http.client.RemoteDisconnected("closed")
            with self.assertRaisesRegex(RuntimeError, "not a confirmed response timeout"):
                client.chat([], [], lambda event: None)

    def test_runtime_passes_supported_thinking_control_and_stage(self):
        fake = Mock()
        fake.inspect.return_value = {"models": [{"name": "qwen3.5:2b"}]}
        fake.json.return_value = {"thinking": {"values": [False, True]}, "capabilities": []}
        fake.chat.return_value = {"role": "assistant", "content": "Hello"}
        events = []
        with tempfile.TemporaryDirectory() as folder:
            with patch("pcs_agent.runtime.Ollama", return_value=fake):
                result = execute("Hello", validate({"model": "qwen3.5:2b", "data_dir": folder}), "", [], events.append)
        self.assertEqual(result["status"], "complete")
        self.assertIs(fake.chat.call_args.kwargs["think"], False)
        self.assertTrue(any(e.get("stage") and "metadata" in e["text"] for e in events))

    def test_old_config_preserves_values_and_is_not_rewritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            raw = json.dumps({"request_timeout": 7, "task_timeout": 60, "model": "qwen3.5:2b"})
            path.write_text(raw)
            value = load(path)
            self.assertEqual(value["request_timeout"], 7)
            # Former 60s default is migrated to 180 so tasks can stay open longer than 59s
            self.assertEqual(value["task_timeout"], 180)
            self.assertEqual(value["model_timeout"], 45)
            # File is rewritten by the migration
            rewritten = json.loads(path.read_text())
            self.assertEqual(rewritten["task_timeout"], 180)
            self.assertEqual(rewritten["request_timeout"], 7)
            self.assertEqual(rewritten["model"], "qwen3.5:2b")

    def test_direct_model_diagnostic_completes_without_tools(self):
        with server_for() as (address, captured):
            config = validate({"ollama_url": address, "model": "qwen3.5:2b", "task_timeout": 5})
            result = run_check(config, emit=lambda s: None)
            self.assertTrue(result["ok"], result)
            payload = next(v for endpoint, v in captured if endpoint == "/api/chat")
            self.assertNotIn("tools", payload)
            self.assertEqual(payload["options"]["num_ctx"], 2048)
            self.assertEqual(payload["options"]["num_predict"], 64)

    def test_diagnostic_deadline_terminates_worker(self):
        result = run_check(validate({}), emit=lambda s: None, worker=stuck_check, timeout=0.5)
        self.assertFalse(result["ok"])
        self.assertIn("deadline", result["error"])
        self.assertEqual(multiprocessing.active_children(), [])

    def test_settings_and_main_console_show_model_wait_and_stage(self):
        from PyQt6.QtWidgets import QApplication
        from pcs_agent.ui import Settings, ConsoleWindow
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            window = ConsoleWindow(validate({"data_dir": folder}), preview=True)
            try:
                dialog = Settings(window.config, window)
                self.assertEqual(dialog.values["model_timeout"].value(), 45)
                dialog.close()
                window.on_event({"kind": "queued", "id": "test", "command": "Hello"})
                window.on_event({"kind": "log", "id": "test", "stage": True, "text": "Reading model metadata..."})
                self.assertIn("Reading model metadata", window.console.toPlainText())
            finally:
                window.close()
                app.processEvents()


if __name__ == "__main__":
    unittest.main()
