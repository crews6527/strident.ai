import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from pcs_agent.config import load, save, validate
from pcs_agent.tools import ToolRunner, direct_command, PageText
from pcs_agent.runtime import execute
from inspect_directory import inventory, report


class ConfigTests(unittest.TestCase):
    def test_roundtrip_single_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            data = validate({"model": "installed:2b", "request_timeout": 5, "num_ctx": 8192})
            save(data, path)
            self.assertEqual(load(path), data)

    def test_preserves_exact_model_and_timeout(self):
        data = validate({"model": "qwen:4b", "request_timeout": 5})
        self.assertEqual(data["model"], "qwen:4b")
        self.assertEqual(data["request_timeout"], 5)

    def test_local_provider_only(self):
        for address in ("https://example.com", "http://example.com", "http://user:pw@localhost:11434", "http://localhost:11434/v1"):
            with self.subTest(address=address), self.assertRaises(ValueError):
                validate({"ollama_url": address})

    def test_invalid_thread_limit(self):
        with self.assertRaises(ValueError):
            validate({"num_thread": 0})

    def test_rejects_scripts_as_app(self):
        with self.assertRaises(ValueError):
            validate({"apps": {"script": str(Path.cwd() / "run.cmd")}})


class RoutingTests(unittest.TestCase):
    def test_app_phrasings(self):
        for text in ("Open Notepad", "Run Notepad", "Launch Notepad", "Start Notepad",
                     "Please open Notepad", "Could you please open Notepad?", "Open Notepad, please"):
            self.assertEqual(direct_command(text), ("open_app", {"app": "Notepad"}))

    def test_web_capability_command(self):
        self.assertEqual(direct_command("Can you access the web?"), ("check_web", {}))
        self.assertEqual(direct_command("Can you check my internet connection please?"), ("check_web", {}))

    def test_multi_task_not_truncated(self):
        self.assertIsNone(direct_command("Open Notepad and search the web"))
        self.assertIsNone(direct_command("Please open Notepad and search the web"))

    def test_open_url(self):
        self.assertEqual(direct_command("Open https://example.com"), ("open_url", {"url": "https://example.com"}))

    def test_bare_domain_open_and_read(self):
        for verb in ("open", "launch", "run", "start"):
            self.assertEqual(direct_command(verb+" promptcopystudio.42web.io"),
                             ("open_url", {"url": "https://promptcopystudio.42web.io"}))
        self.assertEqual(direct_command("read promptcopystudio.42web.io"),
                         ("read_web", {"url": "https://promptcopystudio.42web.io"}))
        self.assertEqual(direct_command("open example.com:8443/path?q=test#section"),
                         ("open_url", {"url": "https://example.com:8443/path?q=test#section"}))
        self.assertEqual(direct_command("Could you please open promptcopystudio.42web.io?"),
                         ("open_url", {"url": "https://promptcopystudio.42web.io"}))

    def test_domain_routing_preserves_executables_and_multiple_tasks(self):
        self.assertEqual(direct_command("open notepad.exe"), ("open_app", {"app": "notepad.exe"}))
        self.assertIsNone(direct_command("open example.com and open Notepad"))
        self.assertIsNone(direct_command("read example.com and summarize its products"))
        self.assertEqual(direct_command("open sales report"), ("open_app", {"app": "sales report"}))

    def test_search_query(self):
        self.assertEqual(direct_command("Search the web for weather Chicago"), ("search_web", {"query": "weather Chicago"}))


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.runner = ToolRunner(validate({"workspace": str(self.workspace)}))

    def tearDown(self):
        self.temp.cleanup()

    def test_workspace_text_read(self):
        (self.workspace / "note.txt").write_text("Hello", encoding="utf-8")
        self.assertEqual(self.runner.read_file("note.txt")["text"], "Hello")

    def test_outside_workspace_denied(self):
        with self.assertRaises(PermissionError):
            self.runner.read_file(str(self.root / "private.txt"))

    def test_attachment_access(self):
        path = self.root / "attached.txt"
        path.write_text("Chosen by user", encoding="utf-8")
        runner = ToolRunner(self.runner.config, str(path))
        self.assertEqual(runner.read_file(str(path))["text"], "Chosen by user")

    def test_binary_rejected(self):
        (self.workspace / "binary.txt").write_bytes(b"hi\0there")
        with self.assertRaises(ValueError):
            self.runner.read_file("binary.txt")

    def test_read_size_is_bounded(self):
        (self.workspace / "large.txt").write_text("a" * 70000)
        result = self.runner.read_file("large.txt")
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["text"]), 64000)

    def test_unknown_tool_denied(self):
        with self.assertRaises(ValueError):
            self.runner.run("shell", {"command": "anything"})

    def test_extra_arguments_denied(self):
        with self.assertRaises(ValueError):
            self.runner.run("open_app", {"app": "Notepad", "shell": True})

    def test_unknown_app_does_not_claim_success(self):
        with patch("pcs_agent.tools.platform.system", return_value="Windows"):
            with self.assertRaises(FileNotFoundError):
                self.runner.open_app("Unknown app")

    def test_app_launch_no_shell_and_evidence(self):
        exe = self.root / "app.exe"
        exe.write_bytes(b"placeholder")
        self.runner.config["apps"] = {"sample": str(exe)}
        fake = Mock(pid=123)
        fake.poll.return_value = None
        with patch("pcs_agent.tools.subprocess.Popen", return_value=fake) as launch, patch("pcs_agent.tools.time.sleep"):
            result = self.runner.open_app("sample")
        self.assertFalse(launch.call_args.kwargs["shell"])
        self.assertEqual(result["pid"], 123)
        self.assertIn("not independently verified", result["verification"])

    def test_app_launcher_failure(self):
        exe = self.root / "app.exe"
        exe.write_bytes(b"placeholder")
        self.runner.config["apps"] = {"sample": str(exe)}
        fake = Mock(pid=123)
        fake.poll.return_value = 1
        with patch("pcs_agent.tools.subprocess.Popen", return_value=fake), patch("pcs_agent.tools.time.sleep"), self.assertRaises(RuntimeError):
            self.runner.open_app("sample")

    def test_browser_failure(self):
        with patch("pcs_agent.tools.webbrowser.open", return_value=False), self.assertRaises(RuntimeError):
            self.runner.open_url("https://example.com")

    def test_search_results_have_sources(self):
        body = "<rss><channel><item><title>Example</title><link>https://example.com</link><description>Text</description></item></channel></rss>"
        with patch("pcs_agent.tools.fetch", return_value=(body, "https://www.bing.com", "xml", False)):
            result = self.runner.search_web("example")
        self.assertEqual(result["results"][0]["url"], "https://example.com")

    def test_html_ignores_scripts(self):
        parser = PageText()
        parser.feed("<h1>Hello</h1><script>secret()</script><p>World</p>")
        self.assertNotIn("secret", "".join(parser.parts))


class RuntimeTests(unittest.TestCase):
    def test_open_bare_domain_handoff_without_model_or_app_lookup(self):
        with patch("pcs_agent.runtime.Ollama") as model, patch("pcs_agent.tools.webbrowser.open", return_value=True) as browser, patch("pcs_agent.tools.ToolRunner.open_app") as app:
            result = execute("open promptcopystudio.42web.io", validate({}), "", [], lambda x: None)
        model.assert_not_called()
        app.assert_not_called()
        browser.assert_called_once_with("https://promptcopystudio.42web.io", new=2)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["evidence"][0]["url"], "https://promptcopystudio.42web.io")

    def test_bare_domain_browser_failure_is_visible_without_model(self):
        with patch("pcs_agent.runtime.Ollama") as model, patch("pcs_agent.tools.webbrowser.open", return_value=False):
            result = execute("open promptcopystudio.42web.io", validate({}), "", [], lambda x: None)
        model.assert_not_called()
        self.assertEqual(result["status"], "needs_attention")

    def test_direct_command_does_not_contact_model(self):
        with patch("pcs_agent.runtime.Ollama") as client:
            result = execute("Help", validate({}), "", [], lambda x: None)
        client.assert_not_called()
        self.assertEqual(result["status"], "complete")

    def test_missing_model_explains_configuration(self):
        with self.assertRaisesRegex(RuntimeError, "Choose an installed"):
            execute("Hello", validate({}), "", [], lambda x: None)

    def test_missing_tag_not_silently_remapped(self):
        fake = Mock()
        fake.inspect.return_value = {"models": [{"name": "other:2b"}]}
        with patch("pcs_agent.runtime.Ollama", return_value=fake), self.assertRaisesRegex(RuntimeError, "not installed"):
            execute("Hello", validate({"model": "requested:4b"}), "", [], lambda x: None)

    def test_tool_error_is_visible(self):
        fake = Mock()
        fake.inspect.return_value = {"models": [{"name": "test:1b"}]}
        fake.json.return_value = {"capabilities": ["tools"]}
        fake.chat.side_effect = [
            {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "open_app", "arguments": {"app": "unknown"}}}]},
            {"role": "assistant", "content": "App not available."}]
        with patch("pcs_agent.runtime.Ollama", return_value=fake), patch("pcs_agent.tools.platform.system", return_value="Windows"):
            result = execute("Please open an unknown app", validate({"model": "test:1b"}), "", [], lambda x: None)
        self.assertEqual(result["status"], "needs_attention")
        self.assertFalse(result["evidence"][0]["ok"])


class InventoryTests(unittest.TestCase):
    def test_candidates_duplicates_and_secret_privacy(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "main.py").write_text('import ui\nTOKEN="MY_SECRET_VALUE"\n', encoding="utf-8")
            (root / "main(3).py").write_bytes((root / "main.py").read_bytes())
            (root / "repair.zip").write_bytes(b"test")
            (root / "config.json").write_text('{"key":"MY_SECRET_VALUE"}')
            (root / "node_modules").mkdir()
            (root / "node_modules" / "ignored.js").write_text("ignored")
            before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
            data = inventory(root)
            output = report(data) + json.dumps(data)
            self.assertNotIn("MY_SECRET_VALUE", output)
            self.assertTrue(data["exact_duplicate_groups"])
            self.assertEqual(len(data["files"]), 4)
            self.assertIn("Download or archive candidate", output)
            after = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
