from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pcs_agent.config import validate
from pcs_agent.runtime import execute
from pcs_agent.storage import State
from pcs_agent.tools import direct_command


SEARCH = {"ok": True, "summary": "Found 6 web results for 'local news'.", "query": "local news",
          "source": "https://www.bing.com/search?format=rss&q=local+news",
          "results": [{"title": f"Source {i}", "url": f"https://example.com/news/{i}",
                       "snippet": f"Actual supplied snippet {i}"} for i in range(1, 7)]}


class SearchResultsTests(unittest.TestCase):
    def test_direct_search_returns_titles_and_urls_without_model(self):
        with patch("pcs_agent.tools.ToolRunner.search_web", return_value=SEARCH), patch("pcs_agent.runtime.Ollama", side_effect=AssertionError("model must not run")):
            result = execute("Search the web for local news", validate({"model": "unavailable:4b"}), "", [], lambda event: None)
        self.assertEqual(result["status"], "complete")
        for item in SEARCH["results"]:
            self.assertIn(item["title"], result["reply"])
            self.assertIn(item["url"], result["reply"])

    def test_followup_uses_saved_evidence_with_no_network_or_model(self):
        with tempfile.TemporaryDirectory() as folder:
            config = validate({"data_dir": folder, "model": "unavailable:4b"})
            state = State(folder)
            state.record_task("82146710", "Search local news", {"status": "complete", "summary": SEARCH["summary"], "evidence": [{"tool": "search_web", **SEARCH}]})
            with patch("pcs_agent.tools.fetch", side_effect=AssertionError("network must not run")), patch("pcs_agent.runtime.Ollama", side_effect=AssertionError("model must not run")):
                result = execute("where are the results?", config, "", [], lambda event: None)
            self.assertEqual(result["status"], "complete")
            self.assertIn("https://example.com/news/6", result["reply"])
            self.assertIn("No new search was run", result["reply"])
            self.assertEqual(result["evidence"][0]["tool"], "show_search_results")
            state.record_task("ae4cf457", "where are the results?", result)
            self.assertEqual(state.search_result()[0], "82146710")

    def test_copied_completion_followup_selects_exact_task(self):
        command = "[82146710] COMPLETE: Found 6 web results for 'today news in columbia, missouri'.\nwhere are the results?"
        self.assertEqual(direct_command(command), ("show_search_results", {"task_id": "82146710"}))
        self.assertIsNone(direct_command(command + " and open Notepad"))

    def test_no_saved_search_explains_next_step_without_model(self):
        with tempfile.TemporaryDirectory() as folder, patch("pcs_agent.runtime.Ollama", side_effect=AssertionError("model must not run")):
            result = execute("Show search results", validate({"data_dir": folder}), "", [], lambda event: None)
        self.assertEqual(result["status"], "needs_attention")
        self.assertIn("No saved web search", result["summary"])

    def test_internet_check_is_a_direct_command(self):
        with patch("pcs_agent.tools.ToolRunner.check_web", return_value={"ok": True, "summary": "Outbound HTTPS is working."}) as check, patch("pcs_agent.runtime.Ollama", side_effect=AssertionError("model must not run")):
            result = execute("Check my internet connection", validate({"model": "unavailable:4b"}), "", [], lambda event: None)
        check.assert_called_once()
        self.assertEqual(result["status"], "complete")
