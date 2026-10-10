import concurrent.futures
import io
import json
import os
from pathlib import Path
import queue
import tempfile
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse
from pypdf import PdfWriter
from pcs_agent.config import validate, import_rc1_settings, load, save
from pcs_agent.gumroad import Gumroad, NoRedirect
from pcs_agent.runtime import Controller, execute
from pcs_agent.storage import State
from pcs_agent.store import Store
from pcs_agent.tools import ToolRunner, direct_command


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = validate({"data_dir": str(self.root / "state"), "workspace": str(self.root)})
        self.store = Store(self.config)

    def product(self, pages=2, title="Sample product"):
        writer = PdfWriter()
        for _ in range(2):
            writer.add_blank_page(width=200, height=200)
        file = self.root / "product.pdf"
        writer.write(file)
        data = {"id": "sample", "title": title, "asset": str(file), "expected_pages": pages,
                "checkout_url": "https://example.com/checkout", "description": "Reviewed description"}
        self.store.save_product(data)
        return data

    def test_pdf_evidence_and_mismatch_status(self):
        p = self.product()
        result = self.store.audit("sample")
        self.assertTrue(result["ok"])
        self.assertEqual(result["audit"]["pages"], 2)
        self.assertEqual(len(result["audit"]["sha256"]), 64)
        self.assertIn("unverified", result["audit"]["scope"])
        p["expected_pages"] = 3
        self.store.save_product(p)
        result = execute("Audit product sample", self.config, "", [], lambda e: None)
        self.assertEqual(result["status"], "needs_attention")
        self.assertIn("expected 3, found 2", result["summary"])
        with self.assertRaises(ValueError):
            self.store.export_listing("sample")

    def test_export_escapes_text_and_never_overwrites(self):
        self.product(title='<script>alert("title")</script>')
        self.store.save_draft("sample", "listing", '<img src=x onerror="alert(1)">')
        one = self.store.export_listing("sample")
        two = self.store.export_listing("sample")
        self.assertNotEqual(one["folder"], two["folder"])
        text = Path(one["files"][0]).read_text()
        self.assertNotIn("<script>", text)
        self.assertNotIn("<img", text)
        self.assertIn("&lt;img", text)
        self.assertFalse(one["published"])
        self.assertIn("unverified", one["verification"])

    def test_export_folder_symlink_rejected(self):
        self.product()
        outside = self.root.parent / (self.root.name + "-outside")
        outside.mkdir()
        self.addCleanup(outside.rmdir)
        (self.root / "store_drafts").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(PermissionError):
            self.store.export_listing("sample")
        self.assertEqual(list(outside.iterdir()), [])

    def make_queue(self):
        root = self.root / "content"
        post = root / "posts" / "ready"
        post.mkdir(parents=True)
        for name, data in (("image.png", b"image fixture"), ("cover.png", b"cover fixture"), ("caption.txt", b"Reviewed caption")):
            (post / name).write_bytes(data)
        manifest = {"schema_version": 1, "account": "prompt_copy_studio", "posts": [
            {"id": "hold", "hold_reason": "Needs review"},
            {"id": "ready", "media": ["image.png"], "cover": "cover.png"}]}
        (root / "manifest.json").write_text(json.dumps(manifest))
        (root / "mark_instagram.py").write_text('raise RuntimeError("legacy script must never run")')
        self.store = Store(self.config | {"instagram_folder": str(root)})
        return root, manifest

    def test_native_instagram_respects_hold_and_runs_no_script(self):
        root, _ = self.make_queue()
        result = self.store.instagram_prepare()
        self.assertEqual(result["post_id"], "ready")
        self.assertEqual(result["caption"], "Reviewed caption")
        self.assertFalse(result["published"])
        self.assertFalse((root / "state.json").exists())
        self.assertEqual(self.store.instagram_queue()["posts"][0]["status"], "hold")

    def test_instagram_cross_post_and_external_paths_rejected(self):
        root, manifest = self.make_queue()
        (root / "outside.png").write_bytes(b"do not read")
        for name in ("../../outside.png", "/etc/passwd"):
            manifest["posts"][1]["media"] = [name]
            (root / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                self.store.instagram_prepare()

    def test_json_import_is_archive_only_deduplicated_and_non_destructive(self):
        history = self.root / "history.json"
        history.write_text(json.dumps([{"role": "assistant", "content": "Old unsupported claim"}]))
        memory = self.root / "memory.json"
        memory.write_text(json.dumps({"store": {"name": {"value": "Prompt Copy Studio"}}}))
        original = memory.read_bytes()
        state = self.store.state
        counts = state.import_personal_data(history, memory)
        self.assertEqual((counts["messages"], counts["facts"]), (1, 1))
        self.assertEqual(state.history(), [])
        self.assertEqual(state.context(), "")
        self.assertEqual(len(state.archived_history()), 1)
        state.confirm_fact("store.name")
        self.assertIn("Prompt Copy Studio", state.context())
        self.assertEqual(state.import_personal_data(history, memory)["already_imported"], 2)
        self.assertEqual(original, memory.read_bytes())

    def test_invalid_import_rolls_back_whole_file(self):
        path = self.root / "history.json"
        path.write_text(json.dumps([{"role": "user", "content": "valid"}, {"role": "system", "content": "invalid"}]))
        with self.assertRaises(ValueError):
            self.store.state.import_personal_data(history_path=path)
        self.assertEqual(self.store.state.archived_history(), [])

    def test_parallel_writes_and_large_evidence_remain_valid(self):
        state = self.store.state
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(lambda i: state.append_messages([{"role": "user", "content": str(i)}]), range(40)))
        self.assertEqual(len(state.history(100)), 40)
        state.record_task("large", "test", {"status": "complete", "summary": "ok", "evidence": ["x" * 70000]})
        with state.connection() as con:
            value = con.execute("SELECT evidence FROM task_log WHERE id='large'").fetchone()[0]
        self.assertTrue(json.loads(value)["truncated"])

    def test_model_cannot_erase_or_replace_confirmed_memory(self):
        state = self.store.state
        state.fact("owner", "Tony", confirmed=True)
        runner = ToolRunner(self.config)
        with self.assertRaises(PermissionError):
            runner.memory_forget("owner")
        with self.assertRaises(PermissionError):
            runner.memory_save("owner", "Someone else")
        self.assertIn("Tony", state.context())
        execute("Forget memory owner", self.config, "", [], lambda e: None)
        self.assertEqual(state.facts(), [])

    def test_explicit_memory_preserves_punctuation(self):
        execute("Remember greeting: Hello!", self.config, "", [], lambda e: None)
        self.assertEqual(self.store.state.facts()[0]["value"], "Hello!")
        self.assertEqual(direct_command("Check store website")[0], "store_website")

    def test_rc1_settings_import_excludes_credentials_scripts_and_identity(self):
        path = self.root / "config.json"
        path.write_text(json.dumps({"schema_version": 1, "ollama_url": "http://127.0.0.1:11434", "model": "exact:2b",
            "GEMINI_API_KEY": "not imported", "instagram_workflow": "legacy.py", "assistant_name": "Old name", "data_dir": "/do-not-copy"}))
        result = import_rc1_settings(path, self.config)
        self.assertEqual(result["model"], "exact:2b")
        self.assertNotIn("GEMINI_API_KEY", result)
        self.assertNotIn("instagram_workflow", result)
        self.assertEqual(result["data_dir"], self.config["data_dir"])
        self.assertEqual(result["assistant_name"], "Strident")

    def test_placeholder_name_updates_without_moving_data(self):
        path = self.root / "config.json"
        previous = self.config | {"assistant_name": "Studio"}
        save(previous, path)
        current = load(path)
        self.assertEqual(current["assistant_name"], "Strident")
        self.assertEqual(current["data_dir"], previous["data_dir"])
        self.assertEqual(current["workspace"], previous["workspace"])
        self.assertEqual(json.loads(path.read_text())["assistant_name"], "Strident")

    def test_spawned_audit_and_history_survive_restart(self):
        self.product()
        events = queue.Queue()
        controller = Controller(events.put, storage=self.store.state)
        try:
            controller.submit("Audit product sample", self.config)
            while True:
                event = events.get(timeout=8)
                if event["kind"] == "result":
                    break
            self.assertEqual(event["status"], "complete")
        finally:
            controller.close()
        restarted = Controller(lambda e: None, storage=State(self.config["data_dir"]))
        try:
            self.assertEqual(restarted.history[0]["content"], "Audit product sample")
            with self.store.state.connection() as con:
                record = con.execute("SELECT * FROM task_log").fetchone()
            self.assertEqual(json.loads(record["evidence"])[0]["audit"]["pages"], 2)
        finally:
            restarted.close()


class GumroadTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"PCS_GUMROAD_TOKEN": "test-session-token"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def opener(self, responses):
        class Fixture:
            requests = []
            def open(self, request, timeout):
                self.requests.append(request)
                result = responses[len(self.requests) - 1]
                if isinstance(result, Exception):
                    raise result
                return io.BytesIO(json.dumps(result).encode())
        return Fixture()

    def test_reviewed_description_changes_only_requested_field(self):
        product = {"id": "abc=", "name": "Sample", "description": "old"}
        fixture = self.opener([{"success": True, "product": product}, {"success": True, "product": product}])
        with patch("urllib.request.build_opener", return_value=fixture):
            result = Gumroad().update_description("abc=", "Reviewed & exact text", "Sample")
        get, put = fixture.requests
        self.assertEqual((get.method, put.method), ("GET", "PUT"))
        self.assertEqual(urllib.parse.parse_qs(put.data.decode()), {"description": ["Reviewed & exact text"]})
        self.assertEqual(put.get_header("Authorization"), "Bearer test-session-token")
        self.assertNotIn("test-session-token", put.full_url + json.dumps(result))
        self.assertEqual(result["fields_changed"], ["description"])

    def test_changed_target_causes_no_write(self):
        fixture = self.opener([{"success": True, "product": {"id": "abc", "name": "Changed name"}}])
        with patch("urllib.request.build_opener", return_value=fixture), self.assertRaises(RuntimeError):
            Gumroad().update_description("abc", "reviewed", "Original")
        self.assertEqual(len(fixture.requests), 1)
        self.assertEqual(fixture.requests[0].method, "GET")

    def test_uncertain_write_not_retried_and_token_not_reported(self):
        fixture = self.opener([{"success": True, "product": {"id": "abc", "name": "Sample"}}, urllib.error.URLError("contains test-session-token")])
        with patch("urllib.request.build_opener", return_value=fixture), self.assertRaises(RuntimeError) as caught:
            Gumroad().update_description("abc", "reviewed", "Sample")
        self.assertIn("uncertain", str(caught.exception))
        self.assertNotIn("test-session-token", str(caught.exception))
        self.assertEqual(len(fixture.requests), 2)

    def test_authenticated_redirect_is_not_forwarded(self):
        with self.assertRaises(RuntimeError):
            NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://elsewhere.example")


if __name__ == "__main__":
    unittest.main()
