import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from pcs_agent.brain import direct_plan, recent_history, TaskTools
from pcs_agent.config import validate
from pcs_agent.provider import Ollama
from pcs_agent.runtime import execute, model_result
from pcs_agent.storage import State


class BrainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = validate({"model": "test:1b", "data_dir": self.temp.name,
                                "workspace": self.temp.name})
        self.client = Mock()
        self.client.inspect.return_value = {"models": [{"name": "test:1b", "digest": "digest-one"}]}
        self.client.json.return_value = {"capabilities": ["tools"], "thinking": {"values": [True, False]}}
        self.client.chat.return_value = {"role": "assistant", "content": "Done."}

    def tearDown(self):
        self.temp.cleanup()

    def run_task(self, command, history=None):
        with patch("pcs_agent.runtime.Ollama", return_value=self.client):
            return execute(command, self.config, "", history or [], lambda _: None)

    def test_explicit_list_bypasses_model_and_runs_all_steps(self):
        result = self.run_task("1. Remember color: blue\n2. Show memory\n3. Help")
        self.client.inspect.assert_not_called()
        self.assertEqual(result["status"], "complete")
        self.assertEqual([e["tool"] for e in result["evidence"]], ["memory_save", "memory_list", "help"])
        self.assertEqual(State(self.temp.name).facts()[0]["status"], "confirmed")
        self.assertEqual(result["metrics"]["model_turns"], 0)

    def test_partial_list_is_left_whole_for_model(self):
        command = "Help\nWrite a new business plan"
        with patch("pcs_agent.runtime.ToolRunner") as runner:
            result = self.run_task(command)
        runner.return_value.run.assert_not_called()
        self.assertEqual([m for m in self.client.chat.call_args.args[0] if m['role'] == 'user'][-1]["content"], command)
        self.assertEqual(result["metrics"]["route"], "model")

    def test_batch_stops_on_first_failure_and_preserves_evidence(self):
        with patch("pcs_agent.tools.ToolRunner.run", side_effect=[{"ok": True, "summary": "First done."}, ValueError("blocked")]) as tool:
            result = self.run_task("Help; Show memory; Help")
        self.assertEqual(tool.call_count, 2)
        self.assertEqual(result["status"], "needs_attention")
        self.assertEqual(len(result["evidence"]), 2)
        self.assertIn("1 steps were not attempted", result["summary"])
        self.assertIn("blocked", result["reply"])

    def test_memory_separators_are_saved_as_data(self):
        for command in ("Remember note: first; Help\nthen second", "/remember note: first; Help\nthen second"):
            self.assertEqual(direct_plan(command), [("memory_save", {"key": "note", "value": "first; Help\nthen second"})])

    def test_url_punctuation_and_quoted_data_not_split(self):
        self.assertEqual(len(direct_plan("https://example.com/?x=a;b")), 1)
        self.assertIsNone(direct_plan('Search for "first; Help"'))
        self.assertIsNone(direct_plan("Open Notepad and Help"))
        self.assertIsNone(direct_plan(";".join(["Help"] * 7)))

    def test_friendly_prefix_keeps_full_command(self):
        self.assertEqual(direct_plan("Strident, please Help then Show memory"), [("help", {}), ("memory_list", {})])

    def test_metadata_cache_rechecks_installed_tag_and_digest(self):
        first = self.run_task("Hello")
        second = self.run_task("Hello")
        self.assertFalse(first["metrics"]["metadata_cached"])
        self.assertTrue(second["metrics"]["metadata_cached"])
        self.assertEqual(self.client.inspect.call_count, 2)
        self.assertEqual(self.client.json.call_count, 1)
        self.client.inspect.return_value = {"models": [{"name": "test:1b", "digest": "digest-two"}]}
        self.run_task("Hello")
        self.assertEqual(self.client.json.call_count, 2)
        self.client.inspect.return_value = {"models": []}
        with self.assertRaisesRegex(RuntimeError, "not installed"):
            self.run_task("Hello")

    def test_missing_digest_always_reads_metadata(self):
        self.client.inspect.return_value = {"models": [{"name": "test:1b"}]}
        self.run_task("Hello")
        self.run_task("Hello")
        self.assertEqual(self.client.json.call_count, 2)

    def test_cache_expiry_endpoint_and_corruption_fall_back(self):
        state = State(self.temp.name)
        state.save_model_metadata("http://localhost:11434", "test:1b", "d", {"capabilities": ["tools"]}, now=1000)
        self.assertIsNotNone(state.model_metadata("http://localhost:11434", "test:1b", "d", now=1100))
        for endpoint, digest, now in (("http://localhost:11435", "d", 1100), ("http://localhost:11434", "x", 1100), ("http://localhost:11434", "d", 1301), ("http://localhost:11434", "d", 999)):
            self.assertIsNone(state.model_metadata(endpoint, "test:1b", digest, now=now))
        with state.connection() as con:
            con.execute("UPDATE model_metadata SET payload='bad json'")
        self.assertIsNone(state.model_metadata("http://localhost:11434", "test:1b", "d", now=1100))

    def test_repeated_model_reads_stop_without_blank_result(self):
        call = {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "memory_list", "arguments": {}}}]}
        self.client.chat.return_value = call
        result = self.run_task("Explain my saved preferences")
        self.assertEqual(result["metrics"]["model_turns"], 3)
        self.assertEqual(result["metrics"]["tool_calls"], 1)
        self.assertEqual(result["metrics"]["reused_reads"], 2)
        self.assertEqual(result["status"], "needs_attention")
        self.assertTrue(result["reply"])
        self.assertTrue(result["evidence"][-1]["reused"])

    def test_full_current_request_preserved_with_large_history(self):
        history = [{"role": role, "content": "z" * 6000} for _ in range(6) for role in ("user", "assistant")]
        command = "Explain this long request: " + "x" * 18000
        self.run_task(command, history)
        messages = self.client.chat.call_args.args[0]
        self.assertEqual([m for m in messages if m['role'] == 'user'][-1]["content"], command)
        self.assertFalse(any(m["content"].startswith("zzz") for m in messages))

    def test_history_keeps_complete_pairs_only(self):
        history = [{"role": "assistant", "content": "orphan"}, {"role": "user", "content": "old"},
                   {"role": "assistant", "content": "old reply"}, {"role": "user", "content": "new"},
                   {"role": "assistant", "content": "new reply"}]
        self.assertEqual(recent_history(history, 12), history[-2:])

    def test_task_memory_prioritizes_relevance_and_skips_large_entries(self):
        state = State(self.temp.name)
        state.fact("aaa", "irrelevant " * 150, confirmed=True)
        state.fact("color", "blue", confirmed=True)
        state.fact("secret proposal", "color red", confirmed=False)
        context = state.context("Tell me about color", max_chars=100)
        self.assertIn("blue", context)
        self.assertNotIn("irrelevant", context)
        self.assertNotIn("red", context)

    def test_model_tool_preview_remains_valid_json(self):
        result = {"ok": True, "summary": "Read.", "text": 'quoted " data ' * 5000}
        preview = json.loads(model_result(result, 4000))
        self.assertTrue(preview["ok"])
        self.assertTrue(preview["truncated_for_context"])
        self.assertNotIn("truncated_for_context", result)

    def test_runtime_inspection_omits_version_only(self):
        client = Ollama(self.config)
        with patch.object(client, "json", return_value={"models": [{"name": "test:1b", "digest": "d"}]}) as request:
            self.assertEqual(client.inspect(include_version=False)["models"][0]["digest"], "d")
        request.assert_called_once_with("/api/tags")


class TaskToolTests(unittest.TestCase):
    def policy(self, command="Do this task"):
        self.runner = Mock()
        self.runner.run.return_value = {"ok": True, "summary": "Done."}
        self.metrics = {"tool_calls": 0, "reused_reads": 0}
        return TaskTools(self.runner, command, self.metrics)

    def test_reads_reused_and_writes_invalidate_them(self):
        policy = self.policy()
        policy.run("store_products", {})
        result, work = policy.run("store_products", {})
        self.assertFalse(work)
        self.assertTrue(result["reused"])
        policy.run("store_save_draft", {"product_id": "a", "channel": "listing", "content": "draft"})
        policy.run("store_products", {})
        self.assertEqual(self.runner.run.call_count, 3)

    def test_identical_successful_side_effect_is_not_repeated(self):
        policy = self.policy()
        args = {"product_id": "a", "channel": "listing", "content": "draft"}
        policy.run("store_save_draft", args)
        result, work = policy.run("store_save_draft", args)
        self.assertFalse(result["ok"])
        self.assertFalse(work)
        self.runner.run.assert_called_once()
        policy = self.policy("Save the draft; do not repeat the action")
        policy.run("store_save_draft", args)
        result, work = policy.run("store_save_draft", args)
        self.assertFalse(work)
        self.assertFalse(result["ok"])
        self.runner.run.assert_called_once()
        policy = self.policy("Repeat this action twice")
        policy.run("store_save_draft", args)
        policy.run("store_save_draft", args)
        self.assertEqual(self.runner.run.call_count, 2)

    def test_failures_have_a_bounded_retry(self):
        policy = self.policy()
        self.runner.run.side_effect = ValueError("Missing file")
        for _ in range(4):
            result, _ = policy.run("read_file", {"path": "missing.txt"})
        self.assertFalse(result["ok"])
        self.assertEqual(self.runner.run.call_count, 2)

    def test_refresh_and_system_health_are_fresh(self):
        policy = self.policy("Refresh twice")
        for _ in range(2):
            policy.run("read_web", {"url": "https://example.com"})
        self.assertEqual(self.runner.run.call_count, 2)
        policy = self.policy()
        for _ in range(2):
            policy.run("system_health", {})
        self.assertEqual(self.runner.run.call_count, 2)

    def test_failed_write_also_invalidates_reads(self):
        policy = self.policy()
        policy.run("store_products", {})
        self.runner.run.return_value = {"ok": False, "summary": "Partial write failed."}
        policy.run("gumroad_products", {})
        policy.run("store_products", {})
        self.assertEqual(self.runner.run.call_count, 3)

    def test_monitoring_request_does_not_reuse_stale_reads(self):
        policy = self.policy("Watch this page for changes")
        for _ in range(2):
            policy.run("read_web", {"url": "https://example.com"})
        self.assertEqual(self.runner.run.call_count, 2)
        policy.run("store_export_listing", {"product_id": "a"})
        result, work = policy.run("store_export_listing", {"product_id": "a"})
        self.assertFalse(work)
        self.assertFalse(result["ok"])
        self.assertEqual(self.runner.run.call_count, 3)


if __name__ == "__main__":
    unittest.main()
