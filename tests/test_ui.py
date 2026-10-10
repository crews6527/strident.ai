import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import tempfile
import time
import unittest
from PyQt6.QtWidgets import QApplication
from pcs_agent.config import validate
from pcs_agent.ui import ConsoleWindow, Settings
from pcs_agent.storage import State
from pypdf import PdfWriter


class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = ConsoleWindow(validate({}), preview=True)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def test_native_console_renders(self):
        self.assertFalse(self.window.grab().isNull())
        self.assertEqual(self.window.tabs.count(), 3)

    def test_navigation_pages(self):
        for title, expected in (("Files", 1), ("Tools", 2), ("Console", 0)):
            self.window.navigate(title)
            self.assertEqual(self.window.pages.currentIndex(), expected)

    def test_status_and_evidence_survive_cancel(self):
        w = self.window
        w.on_event({"id": "t1", "kind": "queued", "command": "Example"})
        w.on_event({"id": "t1", "kind": "started"})
        w.on_event({"id": "t1", "kind": "tool", "name": "open_app", "result": {"ok": True, "summary": "Launcher accepted", "pid": 123}})
        w.on_event({"id": "t1", "kind": "result", "status": "cancelled", "summary": "Stopped", "evidence": []})
        self.assertEqual(w.records["t1"]["evidence"][0]["pid"], 123)
        self.assertIn("cancelled", w.results.toPlainText())

    def test_clear_finished(self):
        w = self.window
        w.on_event({"id": "t1", "kind": "queued", "command": "Help"})
        w.on_event({"id": "t1", "kind": "result", "status": "complete", "summary": "Done", "evidence": []})
        w.clear_finished()
        self.assertEqual(w.queue_list.count(), 0)

    def test_search_links_visible_in_commands_and_results_on_timeout(self):
        w = self.window
        result = {"ok": True, "summary": "Found one result.", "results": [{"title": "Actual source title", "url": "https://example.com/news", "snippet": "Retrieved snippet"}]}
        w.on_event({"id": "t1", "kind": "queued", "command": "Search news"})
        w.on_event({"id": "t1", "kind": "tool", "name": "search_web", "result": result})
        w.on_event({"id": "t1", "kind": "result", "status": "failed", "summary": "Deadline", "evidence": []})
        for text in (w.console.toPlainText(), w.results.toPlainText()):
            self.assertIn("Actual source title", text)
            self.assertIn("https://example.com/news", text)

    def test_direct_search_reply_is_not_printed_twice(self):
        from pcs_agent.tools import format_search_results
        w = self.window
        result = {"ok": True, "summary": "Found one result.", "results": [{"title": "Unique source", "url": "https://example.com/unique", "snippet": "Snippet"}]}
        w.on_event({"id": "t1", "kind": "queued", "command": "Search news"})
        w.on_event({"id": "t1", "kind": "tool", "name": "search_web", "result": result})
        w.on_event({"id": "t1", "kind": "result", "status": "complete", "summary": result["summary"], "reply": format_search_results(result), "evidence": []})
        self.assertEqual(w.console.toPlainText().count("https://example.com/unique"), 1)

    def test_settings_constructs(self):
        dialog = Settings(validate({}), self.window)
        self.assertEqual(dialog.values["num_thread"].value(), 2)
        self.assertEqual(dialog.values["request_timeout"].value(), 15)
        dialog.close()

    def test_gui_to_worker_flow(self):
        self.window.close()
        self.window = ConsoleWindow(validate({}))
        self.window.submit("Help")
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            self.app.processEvents()
            if self.window.records and next(iter(self.window.records.values()))["status"] == "complete":
                break
            time.sleep(0.02)
        record = next(iter(self.window.records.values()))
        self.assertEqual(record["status"], "complete")
        self.assertIn("TOOL EVIDENCE", self.window.results.toPlainText())
        self.assertTrue(record["evidence"][0]["ok"])

    def test_store_form_to_spawned_pdf_audit(self):
        self.window.close()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            writer = PdfWriter()
            writer.add_blank_page(width=200, height=200)
            writer.write(root / "product.pdf")
            config = validate({"data_dir": str(root / "data"), "workspace": str(root), "assistant_name": "My Agent"})
            self.window = ConsoleWindow(config)
            self.window.navigate("Store")
            store = self.window.store_page
            store.new_product()
            store.title.setText("GUI product")
            store.asset.setText(str(root / "product.pdf"))
            store.checkout.setText("https://example.com/buy")
            store.pages.setText("1")
            store.save_product()
            store.audit()
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                self.app.processEvents()
                if self.window.records and next(iter(self.window.records.values()))["status"] == "complete":
                    break
                time.sleep(0.02)
            record = next(iter(self.window.records.values()))
            self.assertEqual(record["status"], "complete")
            self.assertEqual(record["evidence"][0]["audit"]["pages"], 1)
            self.assertIn("My Agent", self.window.windowTitle())
            self.assertFalse(self.window.artwork.pixmap().isNull())
            self.window.close()

    def test_memory_page_review_changes_model_context(self):
        self.window.close()
        with tempfile.TemporaryDirectory() as folder:
            config = validate({"data_dir": folder})
            State(folder).fact("store.name", "Prompt Copy Studio")
            self.window = ConsoleWindow(config, preview=True)
            self.window.navigate("Memory")
            page = self.window.memory_page
            page.facts.setCurrentRow(0)
            self.assertEqual(State(folder).context(), "")
            page.confirm()
            self.assertIn("Prompt Copy Studio", State(folder).context())
            self.window.close()


if __name__ == "__main__":
    unittest.main()
