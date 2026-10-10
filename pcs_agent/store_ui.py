"""Store and memory pages. Remote writes are reviewed in the interface."""
import json
import os
import threading
import uuid
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QLineEdit, QPlainTextEdit, QFormLayout, QFileDialog,
    QMessageBox, QInputDialog, QDialog, QGridLayout)
from .store import Store
from .storage import State
from .gumroad import Gumroad


class RemoteBus(QObject):
    done = pyqtSignal(dict)


class StorePage(QWidget):
    def __init__(self, console):
        super().__init__()
        self.console = console
        self.current_id = ""
        self.bus = RemoteBus()
        self.bus.done.connect(self.remote_done)
        self.updating = False
        root = QVBoxLayout(self)
        title = QLabel("Your store")
        title.setObjectName("title")
        root.addWidget(title)
        root.addWidget(QLabel("Product files, listing drafts and Gumroad. Instagram media stays in your content folder."))
        row = QHBoxLayout()
        for text, callback in (("Refresh", self.refresh), ("Add product", self.new_product),
                               ("Connect Gumroad", self.connect_gumroad), ("Load Gumroad products", lambda: console.submit("Sync Gumroad")),
                               ("Check website", lambda: console.submit("Check store website"))):
            button = QPushButton(text)
            button.clicked.connect(callback)
            row.addWidget(button)
        root.addLayout(row)
        self.products = QListWidget()
        self.products.setMaximumHeight(130)
        self.products.currentRowChanged.connect(self.select)
        root.addWidget(self.products)
        form = QFormLayout()
        self.title = QLineEdit()
        self.checkout = QLineEdit()
        self.pages = QLineEdit()
        self.asset = QLineEdit()
        self.asset.setReadOnly(True)
        self.description = QPlainTextEdit()
        self.description.setMaximumHeight(120)
        self.remote_id = QLabel("Not connected to a Gumroad product")
        for name, widget in (("Product title", self.title), ("Checkout URL", self.checkout),
                             ("Expected total PDF pages", self.pages), ("Product file", self.asset),
                             ("Gumroad product", self.remote_id)):
            form.addRow(name, widget)
        root.addLayout(form)
        row = QHBoxLayout()
        for text, callback in (("Browse product file", self.browse), ("Save product", self.save_product),
                               ("Check file", self.audit), ("Export listing", self.export)):
            button = QPushButton(text)
            button.clicked.connect(callback)
            row.addWidget(button)
        root.addLayout(row)
        root.addWidget(QLabel("Listing description / reviewed draft"))
        root.addWidget(self.description)
        row = QHBoxLayout()
        for text, callback in (("Save listing draft", self.save_draft), ("Load latest draft", self.load_draft),
                               ("Ask agent to draft listing", self.ask_draft)):
            button = QPushButton(text)
            button.clicked.connect(callback)
            row.addWidget(button)
        self.apply_button = QPushButton("Review and update Gumroad description")
        self.apply_button.clicked.connect(self.apply_description)
        row.addWidget(self.apply_button)
        root.addLayout(row)
        self.status = QLabel("Add a product or connect Gumroad. File checks verify your local file; checkout delivery needs a separate check.")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.rows = []

    def store(self):
        return Store(self.console.config)

    def error(self, exc):
        QMessageBox.warning(self, "Store needs attention", str(exc))

    def refresh(self):
        try:
            selected = self.current_id
            self.rows = self.store().state.products()
            self.products.blockSignals(True)
            self.products.clear()
            for p in self.rows:
                self.products.addItem(p["title"] + "  [" + p["id"] + "]")
            self.products.blockSignals(False)
            index = next((i for i, p in enumerate(self.rows) if p["id"] == selected), 0 if self.rows else -1)
            self.products.setCurrentRow(index)
        except Exception as exc:
            self.products.blockSignals(False)
            self.error(exc)

    def select(self, index):
        if not 0 <= index < len(self.rows):
            return
        p = self.rows[index]
        self.current_id = p["id"]
        self.title.setText(p["title"])
        self.asset.setText(p["asset"])
        self.checkout.setText(p["checkout_url"])
        self.pages.setText(str(p["expected_pages"]) if p["expected_pages"] is not None else "")
        self.description.setPlainText(p["description"])
        self.remote_id.setText(p["remote_id"] or "Not connected to a Gumroad product")
        self.apply_button.setEnabled(bool(p["remote_id"]) and not self.updating)

    def new_product(self):
        self.current_id = "product-" + uuid.uuid4().hex[:12]
        self.title.clear()
        self.asset.clear()
        self.checkout.clear()
        self.pages.clear()
        self.description.clear()
        self.remote_id.setText("Not connected to a Gumroad product")
        self.apply_button.setEnabled(False)
        self.status.setText("Enter the product title and choose its file and checkout link, then save.")

    def browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose the product file", self.console.config["workspace"], "Product files (*.pdf *.zip *.docx *.txt);;All files (*)")
        if path:
            self.asset.setText(path)

    def save_product(self):
        try:
            if not self.current_id:
                self.current_id = "product-" + uuid.uuid4().hex[:12]
            existing = next((p for p in self.rows if p["id"] == self.current_id), {})
            self.store().save_product({"id": self.current_id, "title": self.title.text().strip(),
                "asset": self.asset.text(), "checkout_url": self.checkout.text().strip(),
                "expected_pages": int(self.pages.text()) if self.pages.text().strip() else None,
                "description": self.description.toPlainText(), "remote_id": existing.get("remote_id", "")})
            self.status.setText("Product saved locally. No remote listing was changed.")
            self.refresh()
        except Exception as exc:
            self.error(exc)

    def audit(self):
        if self.current_id:
            self.console.submit("Audit product " + self.current_id)

    def export(self):
        if self.current_id:
            self.console.submit("Export listing " + self.current_id)

    def save_draft(self):
        try:
            result = self.store().save_draft(self.current_id, "listing", self.description.toPlainText())
            self.status.setText(result["summary"])
        except Exception as exc:
            self.error(exc)

    def load_draft(self):
        try:
            drafts = [d for d in self.store().state.drafts(self.current_id) if d["channel"] == "listing"]
            if not drafts:
                raise ValueError("No listing draft has been saved for this product.")
            self.description.setPlainText(drafts[0]["content"])
            self.status.setText("Loaded the latest local listing draft. Review before applying it.")
        except Exception as exc:
            self.error(exc)

    def ask_draft(self):
        if self.current_id:
            self.console.submit("Draft listing for " + self.current_id)

    def connect_gumroad(self):
        token, accepted = QInputDialog.getText(self, "Connect Gumroad for this session", "Enter your Gumroad API access token, not your account password.\nIt is kept in memory until this agent closes.", QLineEdit.EchoMode.Password)
        if accepted and token.strip():
            if len(token) > 4096 or "\n" in token or "\r" in token:
                self.error(ValueError("Invalid token format."))
                return
            os.environ["PCS_GUMROAD_TOKEN"] = token.strip()
            self.status.setText("Token set for this session. Load Gumroad products to verify the connection. Nothing has been published.")

    def apply_description(self):
        try:
            if self.updating:
                return
            if self.console.controller and self.console.controller.active:
                raise ValueError("Wait for the active task to finish before reviewing a remote listing update.")
            p = self.store().state.product(self.current_id)
            if not p["remote_id"]:
                raise ValueError("Load Gumroad products and select a connected product first.")
            content = self.description.toPlainText().strip()
            if not 1 <= len(content) <= 12000:
                raise ValueError("Enter the reviewed description first.")
            # QMessageBox details exposes the exact payload before confirmation.
            box = QMessageBox(self)
            box.setWindowTitle("Confirm Gumroad listing update")
            box.setText("Update the description for " + p["title"] + " on Gumroad?")
            box.setInformativeText("Gumroad product: " + p["remote_id"] + "\nOnly the description will change. Review the exact text in Show Details before proceeding.")
            box.setDetailedText(content)
            box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
            box.setDefaultButton(QMessageBox.StandardButton.Cancel)
            if box.exec() != QMessageBox.StandardButton.Yes:
                return
            self.updating = True
            self.update_record = {"id": "remote-" + uuid.uuid4().hex[:12], "product_id": p["remote_id"]}
            self.apply_button.setEnabled(False)
            self.status.setText("Updating the reviewed Gumroad description...")
            def send():
                try:
                    result = Gumroad().update_description(p["remote_id"], content, p["title"])
                except Exception as exc:
                    result = {"ok": False, "summary": str(exc)}
                self.bus.done.emit(result)
            threading.Thread(target=send, name="store-listing-update", daemon=True).start()
        except Exception as exc:
            self.error(exc)

    def remote_done(self, result):
        self.updating = False
        self.apply_button.setEnabled(any(p["id"] == self.current_id and p["remote_id"] for p in self.rows))
        self.status.setText(result["summary"])
        try:
            record = self.update_record
            self.store().state.record_task(record["id"], "Reviewed Gumroad description update: " + record["product_id"],
                {"status": "complete" if result.get("ok") else "needs_attention", "summary": result["summary"], "evidence": [result]})
        except Exception as exc:
            self.console.logs.appendPlainText("Could not save the update receipt: " + str(exc))
        self.console.logs.appendPlainText("Gumroad description update: " + json.dumps(result))
        self.console.latest.setText(result["summary"])


class MemoryPage(QWidget):
    def __init__(self, console):
        super().__init__()
        self.console = console
        root = QVBoxLayout(self)
        title = QLabel("Personal memory")
        title.setObjectName("title")
        root.addWidget(title)
        root.addWidget(QLabel("Imported facts require review. Historical assistant replies are retained as an archive and stay out of new model context."))
        self.facts = QListWidget()
        root.addWidget(self.facts, 1)
        row = QGridLayout()
        for index, (text, callback) in enumerate((("Refresh", self.refresh), ("Import long-term JSON", self.import_memory),
                               ("Import history JSON", self.import_history), ("Confirm selected fact", self.confirm),
                               ("Forget selected fact", self.forget), ("View imported history", self.view_history))):
            b = QPushButton(text)
            b.clicked.connect(callback)
            row.addWidget(b, index // 3, index % 3)
        root.addLayout(row)
        self.status = QLabel("Your database stays on this device. Original JSON files are never modified.")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.rows = []

    def state(self):
        return State(self.console.config["data_dir"])

    def refresh(self):
        try:
            self.rows = self.state().facts()
            self.facts.clear()
            for f in self.rows:
                self.facts.addItem(f"{f['status'].upper()} | {f['key']}\n{f['value']}")
        except Exception as exc:
            QMessageBox.warning(self, "Memory needs attention", str(exc))

    def import_file(self, kind):
        path, _ = QFileDialog.getOpenFileName(self, "Choose personal " + kind + " data", "", "JSON data (*.json)")
        if not path:
            return
        try:
            counts = self.state().import_personal_data(**{kind + "_path": path})
            self.status.setText(f"Imported {counts['messages']} messages and {counts['facts']} facts. Already imported files: {counts['already_imported']}. Originals are unchanged.")
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Import stopped", str(exc))

    def import_memory(self):
        self.import_file("memory")

    def import_history(self):
        self.import_file("history")

    def view_history(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Imported history: latest 200 messages")
        dialog.resize(800, 600)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText("\n\n".join(m["role"].upper() + ": " + m["content"] for m in self.state().archived_history()))
        layout.addWidget(text)
        close = QPushButton("Close")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

    def confirm(self):
        i = self.facts.currentRow()
        if 0 <= i < len(self.rows):
            self.state().confirm_fact(self.rows[i]["key"])
            self.refresh()

    def forget(self):
        i = self.facts.currentRow()
        if 0 <= i < len(self.rows):
            self.state().forget(self.rows[i]["key"])
            self.refresh()
