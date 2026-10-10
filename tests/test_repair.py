import json
import queue
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch
from pcs_agent.config import validate
from pcs_agent.brain import tool_names, direct_plan
from pcs_agent.runtime import Controller, execute
from pcs_agent.storage import State
from pcs_agent.tools import direct_command, schemas
from pcs_agent.tools import fetch, public_url
from pcs_agent.website import audit, check_links, save_report
from pcs_agent.instance import InstanceLock
from pcs_agent.provider import Ollama
from configure_fast_writing import configure


HTML = '''<html><head><title>Prompt Copy Studio</title><meta name="description" content="Practical products"><meta name="viewport" content="width=device-width, initial-scale=1"></head><body><h1>Digital products</h1><p>Useful resources for your small business.</p><a href="/good">Good</a><a href="/missing">Missing</a><a href="/cart">Cart</a><a href="https://checkout.example.com/buy">Buy</a></body></html>'''


def quick_worker(pipe, command, config, attachment, history):
    pipe.send({"kind": "result", "status": "complete", "summary": "Finished", "reply": "Finished", "evidence": []})
    pipe.close()


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = validate({"data_dir": self.temp.name, "workspace": self.temp.name,
                                "model": "task:2b", "text_model": "writing:1b"})

    def tearDown(self):
        self.temp.cleanup()

    def fake(self):
        c = Mock()
        c.inspect.return_value = {"models": [{"name": "task:2b", "digest": "a"}, {"name": "writing:1b", "digest": "b"}]}
        c.json.return_value = {"capabilities": ["tools"], "thinking": {"values": [False, True]}}
        c.chat.return_value = {"role": "assistant", "content": "Clear draft."}
        return c

    def test_common_website_commands_and_full_request_preservation(self):
        expected = {"Check my website": "website_audit", "Open my website": "open_store",
                    "Check my website for broken links": "website_links", "List files": "list_files"}
        for command, tool in expected.items():
            self.assertEqual(direct_command(command)[0], tool)
        for command in ("Check my website and rewrite everything", "Open my website and publish a product"):
            self.assertIsNone(direct_command(command))

    def test_polite_simple_requests_bypass_inference_without_losing_steps(self):
        self.assertEqual(direct_plan("Could you please check my website"), [("website_audit", {"url": ""})])
        self.assertEqual(direct_plan("Strident, can you open my website then list files"), [("open_store", {}), ("list_files", {"path": "."})])
        self.assertIsNone(direct_plan("Could you open my website and publish a product"))

    def test_direct_read_displays_actual_text(self):
        with patch("pcs_agent.tools.fetch", return_value=(HTML, "https://example.com", "text/html", False)), patch("pcs_agent.runtime.Ollama") as model:
            result = execute("Read my website", self.config, "", [], lambda e: None)
        model.assert_not_called()
        self.assertIn("Digital products", result["reply"])
        self.assertIn("https://example.com", result["reply"])

    def test_website_audit_runs_without_model(self):
        with patch("pcs_agent.website.fetch", return_value=(HTML, "https://example.com", "text/html", False)), patch("pcs_agent.runtime.Ollama") as model:
            result = execute("Check my website", self.config, "", [], lambda e: None)
        model.assert_not_called()
        self.assertEqual(result["status"], "complete")
        self.assertIn("Prompt Copy Studio", result["reply"])
        self.assertEqual(result["evidence"][0]["issues"], [])

    def test_audit_reports_missing_metadata(self):
        with patch("pcs_agent.website.fetch", return_value=("<html><p>hello</p></html>", "https://example.com", "text/html", False)):
            result = audit("https://example.com")
        self.assertTrue(result["ok"])
        self.assertIn("Page title is missing.", result["issues"])

    def test_challenge_is_not_claimed_as_website_content(self):
        with patch("pcs_agent.website.fetch", return_value=("<html><title>Just a moment...</title><p>Verify you are human</p></html>", "https://example.com", "text/html", False)):
            self.assertFalse(audit("https://example.com")["ok"])

    def test_http_403_explains_host_access(self):
        with patch("pcs_agent.website.fetch", side_effect=urllib.error.HTTPError("https://example.com", 403, "Forbidden", {}, None)):
            result = audit("https://example.com")
        self.assertFalse(result["ok"])
        self.assertEqual(result["http_status"], 403)

    def test_known_host_cookie_is_bounded_and_scripts_not_executed(self):
        # NIST AES-CBC first-block test vector.
        challenge = '<script src="/aes.js"></script><script>var a=toNumbers("2b7e151628aed2a6abf7158809cf4f3c"),b=toNumbers("000102030405060708090a0b0c0d0e0f"),c=toNumbers("7649abac8119b246cee98e9b12e9197d");document.cookie="__test="+toHex(slowAES.decrypt(c,2,a,b));</script>'
        with patch("pcs_agent.tools._fetch_once", side_effect=[(challenge, "https://example.com", "text/html", False), (HTML, "https://example.com", "text/html", False)]) as request:
            result = fetch("https://example.com", browser_cookie=True)
        self.assertEqual(result[0], HTML)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args.args[3], "__test=6bc1bee22e409f96e93d7e117393172a")
        with patch("pcs_agent.tools._fetch_once", return_value=(challenge, "https://example.com", "text/html", False)) as request:
            with self.assertRaisesRegex(RuntimeError, "requires a browser"):
                fetch("https://example.com")
        self.assertEqual(request.call_count, 1)

    def test_private_network_urls_are_rejected(self):
        for url in ("http://127.0.0.1:8766/api/alerts", "http://localhost", "http://10.0.0.1", "http://[::1]"):
            with self.assertRaises(ValueError):
                public_url(url)

    def test_cookie_is_not_forwarded_across_origins(self):
        challenge = '<script src="/aes.js"></script>__test= slowAES.decrypt(c,2,a,b)'
        with patch("pcs_agent.tools._fetch_once", return_value=(challenge, "https://other.example.com", "text/html", False)) as request:
            with self.assertRaisesRegex(RuntimeError, "another origin"):
                fetch("https://example.com", browser_cookie=True)
        self.assertEqual(request.call_count, 1)

    def test_link_check_skips_checkout_external_and_query_actions(self):
        calls = []
        def fetch(url, **kwargs):
            calls.append(url)
            if url.endswith("missing"):
                raise urllib.error.HTTPError(url, 404, "Not found", {}, None)
            return HTML, url, "text/html", False
        with patch("pcs_agent.website.fetch", side_effect=fetch):
            result = check_links("https://example.com")
        self.assertEqual(calls, ["https://example.com", "https://example.com/good", "https://example.com/missing"])
        self.assertEqual(len(result["skipped_links"]), 2)
        self.assertEqual(result["checked_links"][1]["classification"], "broken")

    def test_reports_save_evidence_without_new_requests_and_do_not_overwrite(self):
        s = State(self.temp.name)
        s.record_task("1234abcd", "Check my website", {"status": "complete", "summary": "Checked", "evidence": [{"tool": "website_audit", "ok": True, "summary": "Checked", "report_text": "A real finding", "checked_utc": "2026-10-09"}]})
        with patch("pcs_agent.website.fetch") as fetch:
            a, b = save_report(self.config), save_report(self.config)
        fetch.assert_not_called()
        self.assertNotEqual(a["folder"], b["folder"])
        self.assertIn("A real finding", Path(a["files"][0]).read_text())

    def test_greeting_uses_only_explicit_writing_model_no_tools(self):
        client = self.fake()
        with patch("pcs_agent.runtime.Ollama", return_value=client) as provider:
            execute("Hello", self.config, "", [], lambda e: None)
        self.assertEqual(provider.call_args.args[0]["model"], "writing:1b")
        self.assertEqual(client.chat.call_args.args[1], [])
        self.assertEqual(self.config["model"], "task:2b")

    def test_friendly_writing_phrases_use_small_text_menu(self):
        for text in ("Could you please write a short welcome message", "Strident, can you explain marketing", "How are you?"):
            self.assertEqual(tool_names(text), set())

    def test_unknown_writing_model_is_not_substituted(self):
        client = self.fake()
        config = self.config | {"text_model": "missing:1b"}
        with patch("pcs_agent.runtime.Ollama", return_value=client), self.assertRaisesRegex(RuntimeError, "not installed"):
            execute("Hello", config, "", [], lambda e: None)
        client.chat.assert_not_called()

    def test_tool_menus_smaller_and_unoffered_call_is_rejected(self):
        menu = schemas(tool_names("Check the website and explain its links"))
        self.assertLess(len(json.dumps(menu)), len(json.dumps(schemas())) // 2)
        client = self.fake()
        client.chat.side_effect = [{"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "open_app", "arguments": {"app": "notepad"}}}]}, {"role": "assistant", "content": "Unavailable."}]
        with patch("pcs_agent.runtime.Ollama", return_value=client), patch("pcs_agent.tools.ToolRunner.open_app") as app:
            result = execute("Explain this website", self.config, "", [], lambda e: None)
        app.assert_not_called()
        self.assertEqual(result["status"], "needs_attention")

    def test_checked_website_review_keeps_report_when_writing_fails(self):
        with patch("pcs_agent.website.fetch", return_value=(HTML, "https://example.com", "text/html", False)), patch("pcs_agent.runtime.Ollama", side_effect=RuntimeError("model failed")):
            result = execute("Review my website and suggest improvements", self.config, "", [], lambda e: None)
        self.assertEqual(result["status"], "needs_attention")
        self.assertIn("Prompt Copy Studio", result["reply"])
        self.assertEqual(len(result["evidence"]), 1)

    def test_checked_listing_uses_facts_and_saves_local_draft(self):
        p = Path(self.temp.name) / "book.txt"
        p.write_text("Useful book")
        from pcs_agent.store import Store
        Store(self.config).save_product({"id": "book", "title": "Book", "asset": str(p), "checkout_url": "https://example.com/book"})
        client = self.fake()
        with patch("pcs_agent.runtime.Ollama", return_value=client):
            result = execute("Draft listing for book", self.config, "", [], lambda e: None)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(client.chat.call_args.args[1], [])
        self.assertEqual(State(self.temp.name).drafts("book")[0]["content"], "Clear draft.")
        self.assertFalse(result["evidence"][-1]["published"])

    def test_no_truncated_listing_saved(self):
        from pcs_agent.store import Store
        p = Path(self.temp.name) / "book.txt"
        p.write_text("Useful book")
        Store(self.config).save_product({"id": "book", "title": "Book", "asset": str(p), "checkout_url": "https://example.com/book"})
        client = self.fake()
        client.chat.return_value = {"role": "assistant", "content": "Partial", "output_truncated": True}
        with patch("pcs_agent.runtime.Ollama", return_value=client):
            result = execute("Draft listing for book", self.config, "", [], lambda e: None)
        self.assertEqual(result["status"], "needs_attention")
        self.assertEqual(State(self.temp.name).drafts("book"), [])

    def test_fast_setup_only_selects_installed_model_after_completed_probe(self):
        client = Mock()
        client.inspect.return_value = {"models": [{"name": "tiny:1b", "size_gb": .8}, {"name": "task:2b", "size_gb": 2.6}]}
        save = Mock()
        checker = Mock(return_value={"ok": True, "reply": "Hello", "elapsed": 2})
        self.assertTrue(configure(self.config | {"text_model": ""}, client=client, checker=checker, save_config=save, emit=lambda s: None))
        self.assertEqual(save.call_args.args[0]["text_model"], "tiny:1b")
        self.assertEqual(save.call_args.args[0]["model"], "task:2b")
        self.assertEqual(checker.call_args.args[0]["model"], "tiny:1b")
        checker.return_value = {"ok": False, "error": "timeout"}
        save.reset_mock()
        self.assertFalse(configure(self.config | {"text_model": ""}, client=client, checker=checker, save_config=save, emit=lambda s: None))
        save.assert_not_called()

    def test_os_instance_lock_releases_without_deleting_file(self):
        lock = InstanceLock(self.temp.name)
        with self.assertRaisesRegex(RuntimeError, "already running"):
            InstanceLock(self.temp.name)
        lock.close()
        next_lock = InstanceLock(self.temp.name)
        next_lock.close()

    def test_streamed_reasoning_retained_for_tool_followup_without_display(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.__iter__ = Mock(return_value=iter([
            (json.dumps({"message": {"thinking": "internal test trace"}, "done": False}) + "\n").encode(),
            (json.dumps({"message": {"tool_calls": [{"function": {"name": "read_web", "arguments": {"url": "https://example.com"}}}]}, "done": True}) + "\n").encode()]))
        events = []
        with patch.object(Ollama, "_open", return_value=response):
            message = Ollama(self.config).chat([], [], events.append)
        self.assertEqual(message["thinking"], "internal test trace")
        self.assertNotIn("internal test trace", str(events))

    def test_existing_writing_selection_is_preserved(self):
        client = Mock()
        save = Mock()
        self.assertTrue(configure(self.config, client=client, save_config=save, emit=lambda s: None))
        client.inspect.assert_not_called()
        save.assert_not_called()

    def test_more_than_twenty_completed_tasks_do_not_fill_queue(self):
        events = queue.Queue()
        controller = Controller(events.put, worker=quick_worker)
        try:
            for _ in range(25):
                controller.submit("quick", self.config)
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if events.get(timeout=5)["kind"] == "result":
                        break
                else:
                    self.fail("Worker did not finish")
            self.assertEqual(sum(not task.finished for task in controller.tasks.values()), 0)
            self.assertTrue(controller.thread.is_alive())
        finally:
            controller.close()

    def test_callback_exception_does_not_kill_queue(self):
        events = queue.Queue()
        def callback(event):
            if event["kind"] == "started":
                raise ValueError("display failure")
            events.put(event)
        controller = Controller(callback, worker=quick_worker)
        try:
            with self.assertLogs(level="ERROR"):
                controller.submit("quick", self.config)
                while events.get(timeout=5)["kind"] != "result":
                    pass
            self.assertTrue(controller.thread.is_alive())
        finally:
            controller.close()


if __name__ == "__main__":
    unittest.main()
