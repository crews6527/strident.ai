from __future__ import annotations
import json
import os
import threading
import time
from pathlib import Path
import psutil
from PyQt6.QtCore import Qt, QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor, QIcon, QPixmap, QAction
from PyQt6.QtWidgets import (QDialog, QFileDialog, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPlainTextEdit, QPushButton, QComboBox, QSpinBox, QSplitter, QStackedWidget,
    QTabWidget, QVBoxLayout, QWidget, QScrollArea, QSystemTrayIcon, QMenu)
from .config import config_path, save, validate, import_rc1_settings
from .provider import Ollama
from .runtime import Controller
from .tools import TOOLS, format_search_results, format_tool_result
from .storage import State
from .store_ui import StorePage, MemoryPage
from .curbsentry_ui import CurbSentryPage
from . import __version__


STYLE = """
QWidget { background: #111820; color: #dbe5ed; font-family: 'Segoe UI'; font-size: 13px; }
QMainWindow, QDialog { background: #0c121a; }
QFrame#panel { background: #111b25; border: 1px solid #25313e; border-radius: 10px; }
QLabel#brand { color: #f3f7fb; font-size: 23px; font-weight: 700; letter-spacing: 2px; }
QLabel#title { font-size: 24px; font-weight: 600; color: #f0f5fa; }
QLabel#muted { color: #8c9caa; }
QLabel#teal { color: #65dec6; font-weight: 600; }
QLabel#eyebrow { color: #8ca4b8; font-size: 11px; font-weight: 600; letter-spacing: 1px; }
QPushButton { background: #182430; border: 1px solid #2b3b4b; border-radius: 6px; padding: 9px 13px; }
QPushButton:hover { background: #243647; border-color: #4c7b81; }
QPushButton:disabled { color: #536270; background: #131d27; }
QPushButton#primary { color: #062522; background: #6be0c7; border: none; font-weight: 700; }
QPushButton#nav { text-align: left; background: transparent; border: none; padding: 13px; }
QPushButton#nav:checked { color: #7ce5d1; background: #173332; }
QLineEdit, QPlainTextEdit, QListWidget, QComboBox, QSpinBox { background: #0c141d; border: 1px solid #293b4a; border-radius: 6px; padding: 8px; selection-background-color: #275c5c; }
QPlainTextEdit { font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 13px; }
QListWidget::item { padding: 10px 5px; border-bottom: 1px solid #1f2d39; }
QListWidget::item:selected { background: #193c3c; color: #91efdb; }
QTabWidget::pane { border: 1px solid #293744; border-radius: 6px; }
QTabBar::tab { background: #14202c; padding: 10px 20px; color: #91a3b5; }
QTabBar::tab:selected { color: #76e3cf; background: #1c3038; border-bottom: 2px solid #76e3cf; }
QSplitter::handle { background: #0c121a; width: 12px; }
QScrollBar:vertical { background: #101a23; width: 10px; }
QScrollBar::handle:vertical { background: #304553; min-height: 30px; border-radius: 4px; }
"""


def label(text, kind="", wrap=False):
    widget = QLabel(text)
    if kind:
        widget.setObjectName(kind)
    widget.setWordWrap(wrap)
    return widget


def panel():
    frame = QFrame()
    frame.setObjectName("panel")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(12)
    return frame, layout


class Bus(QObject):
    event = pyqtSignal(dict)
    models = pyqtSignal(dict)


class Settings(QDialog):
    def __init__(self, config, parent):
        super().__init__(parent)
        self.setWindowTitle("Strident.AI settings")
        self.resize(700, 780)
        self.config = dict(config)
        self.bus = Bus()
        self.bus.models.connect(self.models_ready)
        root = QVBoxLayout(self)
        root.addWidget(label("Runtime settings", "title"))
        root.addWidget(label("One configuration file. No automatic provider fallback.", "muted"))
        form = QFormLayout()
        self.address = QLineEdit(config["ollama_url"])
        form.addRow("Local Ollama", self.address)
        row = QHBoxLayout()
        self.models = QComboBox()
        self.models.setEditable(True)
        self.models.addItem(config["model"])
        self.refresh = QPushButton("Refresh installed models")
        self.refresh.clicked.connect(self.fetch_models)
        row.addWidget(self.models, 1)
        row.addWidget(self.refresh)
        form.addRow("Model (exact name)", row)
        self.text_models = QComboBox()
        self.text_models.setEditable(True)
        self.text_models.addItem(config.get("text_model", ""))
        form.addRow("Writing model (blank uses task model)", self.text_models)
        self.probe = QPushButton("Test writing model")
        self.probe.clicked.connect(self.test_model)
        form.addRow("", self.probe)
        self.values = {}
        for key, title, low, high in (("num_thread", "Inference CPU threads", 1, 32),
                    ("num_ctx", "Context tokens", 1024, 32768), ("num_predict", "Maximum reply tokens", 64, 4096),
                    ("request_timeout", "Network read timeout (seconds)", 2, 120),
                    ("model_timeout", "Model response wait (seconds)", 2, 120),
                    ("task_timeout", "Whole task deadline (seconds)", 5, 300)):
            spin = QSpinBox()
            spin.setRange(low, high)
            spin.setValue(config[key])
            self.values[key] = spin
            form.addRow(title, spin)
        self.keep = QComboBox()
        self.keep.addItems(["0", "30s", "1m", "5m"])
        self.keep.setCurrentText(config["keep_alive"])
        form.addRow("Model loaded after reply", self.keep)
        self.workspace = QLineEdit(config["workspace"])
        form.addRow("Workspace folder", self.workspace)
        self.instagram = QLineEdit(config["instagram_folder"])
        form.addRow("Instagram content folder", self.instagram)
        self.store_url = QLineEdit(config["store_url"])
        form.addRow("Store website", self.store_url)
        self.assistant_name = QLineEdit(config["assistant_name"])
        form.addRow("Agent display name", self.assistant_name)
        root.addLayout(form)
        root.addWidget(label("Model requests use a separate response wait. The whole task deadline still stops the worker. Metadata uses the network timeout.", "muted", True))
        root.addWidget(label("Custom apps: name to absolute .exe path (JSON)", "eyebrow"))
        self.apps = QPlainTextEdit(json.dumps(config["apps"], indent=2))
        self.apps.setPlaceholderText('{"google chrome": "C:\\\\Program Files\\\\Google\\\\Chrome\\\\Application\\\\chrome.exe"}')
        self.apps.setMaximumHeight(100)
        root.addWidget(self.apps)
        self.status = label("Refresh models to verify the local connection.", "muted", True)
        root.addWidget(self.status)
        row = QHBoxLayout()
        row.addWidget(label(str(config_path()), "muted", True), 1)
        migrate = QPushButton("Load RC1 settings")
        migrate.clicked.connect(self.import_settings)
        row.addWidget(migrate)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        commit = QPushButton("Save settings")
        commit.setObjectName("primary")
        commit.clicked.connect(self.commit)
        row.addWidget(cancel)
        row.addWidget(commit)
        root.addLayout(row)

    def import_settings(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose the console RC1 config.json", "", "JSON settings (*.json)")
        if not path:
            return
        try:
            data = import_rc1_settings(path, self.config)
            self.address.setText(data["ollama_url"])
            self.models.setCurrentText(data["model"])
            self.workspace.setText(data["workspace"])
            self.apps.setPlainText(json.dumps(data["apps"], indent=2))
            self.keep.setCurrentText(data["keep_alive"])
            for key, spin in self.values.items():
                spin.setValue(data[key])
            self.status.setText("Loaded only local model, workspace, resource and executable settings. Review and save to apply. Original settings are unchanged.")
        except Exception as exc:
            self.status.setText(str(exc))

    def fetch_models(self):
        try:
            config = validate(self.config | {"ollama_url": self.address.text().strip()})
        except Exception as exc:
            self.status.setText(str(exc))
            return
        self.refresh.setEnabled(False)
        self.status.setText("Checking installed models...")
        def fetch():
            try:
                result = {"ok": True, **Ollama(config).inspect()}
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}
            self.bus.models.emit(result)
        threading.Thread(target=fetch, daemon=True).start()

    def models_ready(self, result):
        if "probe_progress" in result:
            self.status.setText(result["probe_progress"])
            return
        if "probe_result" in result:
            self.probe.setEnabled(True)
            check = result["probe_result"]
            self.status.setText(("PASS: " + check.get("reply", "") + f" ({check.get('elapsed', '?')}s)") if check["ok"] else "FAILED: " + check["error"])
            return
        self.refresh.setEnabled(True)
        if result["ok"]:
            previous = self.models.currentText()
            self.models.clear()
            self.models.addItems(list(dict.fromkeys(m["name"] for m in result["models"])))
            writing = self.text_models.currentText()
            self.text_models.clear()
            self.text_models.addItems([""] + list(dict.fromkeys(m["name"] for m in result["models"])))
            self.text_models.setCurrentText(writing)
            if previous:
                self.models.setCurrentText(previous)
            self.status.setText(f"Ollama {result['version']} | {len(result['models'])} installed models. Select one that fits your device.")
        else:
            self.status.setText(result["error"])

    def test_model(self):
        try:
            data = self.config | {"ollama_url": self.address.text().strip(),
                                  "model": self.text_models.currentText().strip() or self.models.currentText().strip()}
            data.update({k: s.value() for k, s in self.values.items()})
            data = validate(data)
            if not data["model"]:
                raise ValueError("Select an installed model first.")
        except Exception as exc:
            self.status.setText(str(exc))
            return
        self.probe.setEnabled(False)
        self.status.setText("Testing a short reply; settings are unchanged until you save.")
        def work():
            from diagnose_ollama import run_check
            def send(value):
                try:
                    self.bus.models.emit(value)
                except RuntimeError:
                    pass
            result = run_check(data, emit=lambda line: send({"probe_progress": line}))
            send({"probe_result": result})
        threading.Thread(target=work, name="writing-model-check", daemon=True).start()

    def commit(self):
        try:
            data = self.config | {"ollama_url": self.address.text().strip(), "model": self.models.currentText().strip(),
                    "text_model": self.text_models.currentText().strip(),
                    "workspace": self.workspace.text().strip(), "instagram_folder": self.instagram.text().strip(),
                    "store_url": self.store_url.text().strip(), "assistant_name": self.assistant_name.text().strip(),
                    "apps": json.loads(self.apps.toPlainText()), "keep_alive": self.keep.currentText()}
            data.update({k: s.value() for k, s in self.values.items()})
            self.config = validate(data)
            save(self.config)
        except Exception as exc:
            QMessageBox.warning(self, "Settings need attention", str(exc))
            return
        self.accept()


class ConsoleWindow(QMainWindow):
    def __init__(self, config, *, preview=False):
        super().__init__()
        self.config = config
        self.preview = preview
        self.records = {}
        self.attachment = ""
        self.bus = Bus()
        self.bus.event.connect(self.on_event)
        self.controller = None if preview else Controller(self.bus.event.emit, storage=State(config["data_dir"]))
        try:
            self.process = psutil.Process()
            self.process.cpu_percent()
        except psutil.Error:
            self.process = None
        psutil.cpu_percent()
        self.setWindowTitle(config["assistant_name"] + " | Strident.AI")
        self.setWindowIcon(QIcon(str(Path(__file__).resolve().parent.parent / "assets" / "face.png")))
        self.setMinimumSize(1000, 680)
        self.resize(1440, 880)
        self.setStyleSheet(STYLE)
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(20)
        header = QHBoxLayout()
        self.artwork = QLabel()
        self.artwork.setPixmap(QPixmap(str(Path(__file__).resolve().parent.parent / "assets" / "face.png")).scaled(56, 56, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.artwork.setToolTip("Your Strident portrait")
        header.addWidget(self.artwork)
        self.brand = label(config["assistant_name"].upper(), "brand")
        header.addWidget(self.brand)
        header.addWidget(label("  /  PROMPT COPY STUDIO", "muted"))
        header.addStretch()
        self.mode = label("BUILD " + __version__, "teal")
        header.addWidget(self.mode)
        outer.addLayout(header)
        split = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(split, 1)
        sidebar, side = panel()
        sidebar.setMinimumWidth(170)
        sidebar.setMaximumWidth(240)
        side.addWidget(label("WORKSPACE", "eyebrow"))
        self.nav = {}
        for title in ("Console", "Website", "Store", "Memory", "CurbSentry", "Task queue", "Files", "Tools", "Settings"):
            button = QPushButton(title)
            button.setObjectName("nav")
            button.setCheckable(True)
            button.clicked.connect(lambda checked, t=title: self.navigate(t))
            self.nav[title] = button
            side.addWidget(button)
        self.nav["Console"].setChecked(True)
        side.addStretch()
        side.addWidget(label("PROJECTS", "eyebrow"))
        side.addWidget(label("Strident.AI", "teal", True))
        side.addWidget(label("Product records\nListing drafts\nInstagram content", "muted", True))
        side.addStretch()
        side.addWidget(label("Voice is off\nUse Windows dictation on demand", "muted", True))
        side.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize)
        sidebar_scroll = QScrollArea()
        sidebar_scroll.setWidgetResizable(True)
        sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sidebar_scroll.setMinimumWidth(170)
        sidebar_scroll.setMaximumWidth(260)
        sidebar_scroll.setWidget(sidebar)
        split.addWidget(sidebar_scroll)
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(8, 0, 8, 0)
        center_layout.setSpacing(12)
        center_layout.addWidget(label("Task console", "title"))
        center_layout.addWidget(label("Run commands. Follow progress. Review the evidence.", "muted"))
        self.pages = QStackedWidget()
        center_layout.addWidget(self.pages, 1)
        self.tabs = QTabWidget()
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.document().setMaximumBlockCount(1500)
        self.console.setPlainText("Strident.AI is ready.\n\nNo task is running. No microphone is active.\n\nTry Open Notepad, Check my internet connection, or Help.\nSelect an installed local model in Settings for conversation and multi-step tasks.\n")
        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.document().setMaximumBlockCount(1500)
        self.results = QPlainTextEdit()
        self.results.setReadOnly(True)
        self.results.setPlaceholderText("Select a task to view its response and tool evidence.")
        for name, widget in (("Commands", self.console), ("Logs", self.logs), ("Results", self.results)):
            self.tabs.addTab(widget, name)
        self.pages.addWidget(self.tabs)
        self.file_page = QWidget()
        files = QVBoxLayout(self.file_page)
        files.addWidget(label("Workspace files", "title"))
        self.folder_label = label(config["workspace"], "muted", True)
        files.addWidget(self.folder_label)
        refresh = QPushButton("Refresh folder")
        refresh.clicked.connect(self.refresh_files)
        files.addWidget(refresh)
        self.file_list = QListWidget()
        self.file_list.itemDoubleClicked.connect(self.attach_workspace_file)
        files.addWidget(self.file_list, 1)
        files.addWidget(label("Double-click a text file to attach it. Use Attach for a file outside this folder.", "muted", True))
        self.pages.addWidget(self.file_page)
        tool_page = QWidget()
        tools_layout = QVBoxLayout(tool_page)
        tools_layout.addWidget(label("Available tools", "title"))
        listing = QPlainTextEdit()
        listing.setReadOnly(True)
        listing.setPlainText("\n\n".join(f"{n}\n{d}" for n, d, _ in TOOLS) +
                "\n\nMigration pending: Ring cameras, signed-in browser automation, legacy PDF/Office processing and speech playback. These are not advertised to the model as available.")
        tools_layout.addWidget(listing)
        self.pages.addWidget(tool_page)
        self.store_page = StorePage(self)
        self.memory_page = MemoryPage(self)
        for page in (self.store_page, self.memory_page):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            self.pages.addWidget(scroll)
        self.curbsentry_page = CurbSentryPage(self)
        self.pages.addWidget(self.curbsentry_page)
        website_page = QWidget()
        site = QVBoxLayout(website_page)
        site.addWidget(label("Website assistant", "title"))
        self.site_label = label(config["store_url"], "teal", True)
        site.addWidget(self.site_label)
        site.addWidget(label("Read your public pages, find issues, check links and prepare local drafts. Choose your website URL in Settings.", "muted", True))
        for title, command in (("Read website", "Read my website"), ("Audit website", "Check my website"),
            ("Check page links", "Check my website for broken links"), ("Suggest improvements", "Review my website and suggest improvements"),
            ("Save latest report", "Save website report"), ("Open website", "Open my website")):
            button = QPushButton(title)
            button.clicked.connect(lambda checked, text=command: self.submit(text))
            site.addWidget(button)
        site.addWidget(label("Public page checks work without Ollama. Suggestions use the writing model. Hosting edits need a hosting connection; this release exports reports and product listings for review.", "muted", True))
        site.addStretch()
        self.pages.addWidget(website_page)
        result_panel, result_layout = panel()
        result_layout.addWidget(label("LATEST RESULT", "eyebrow"))
        self.latest = label("No completed tasks yet.", "muted", True)
        result_layout.addWidget(self.latest)
        center_layout.addWidget(result_panel)
        split.addWidget(center)
        rail = QWidget()
        rail.setMinimumWidth(250)
        rail.setMaximumWidth(350)
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(0, 0, 0, 0)
        task_panel, task_layout = panel()
        task_layout.addWidget(label("TASK QUEUE", "eyebrow"))
        self.queue_list = QListWidget()
        self.queue_list.currentItemChanged.connect(self.show_task)
        task_layout.addWidget(self.queue_list, 1)
        clear = QPushButton("Clear finished tasks")
        clear.clicked.connect(self.clear_finished)
        task_layout.addWidget(clear)
        rail_layout.addWidget(task_panel, 1)
        health_panel, health = panel()
        health.addWidget(label("SYSTEM HEALTH", "eyebrow"))
        self.health = label("Waiting for first resource sample...", "muted", True)
        health.addWidget(self.health)
        self.model_label = label("Model: " + (config["model"] or "not selected"), "muted", True)
        health.addWidget(self.model_label)
        health.addWidget(label("Voice: off\nQueue: one active task\nIdle inference: off", "teal", True))
        check = QPushButton("Check web connection")
        check.clicked.connect(lambda: self.submit("Check my internet connection"))
        health.addWidget(check)
        rail_layout.addWidget(health_panel)
        split.addWidget(rail)
        split.setSizes([190, 850, 290])
        bottom, compose = panel()
        compose.setSpacing(8)
        row = QHBoxLayout()
        self.command = QLineEdit()
        self.command.setPlaceholderText("Ask " + config["assistant_name"] + " or enter a command...")
        self.command.returnPressed.connect(self.submit_input)
        self.command.setMinimumHeight(44)
        row.addWidget(self.command, 1)
        self.run_button = QPushButton("Run  ↵")
        self.run_button.setObjectName("primary")
        self.run_button.clicked.connect(self.submit_input)
        row.addWidget(self.run_button)
        compose.addLayout(row)
        row = QHBoxLayout()
        attach = QPushButton("Attach")
        attach.clicked.connect(self.attach)
        row.addWidget(attach)
        self.attach_label = label("No file attached", "muted")
        row.addWidget(self.attach_label)
        detach = QPushButton("Clear attachment")
        detach.clicked.connect(lambda: self.set_attachment(""))
        row.addWidget(detach)
        dictate = QPushButton("Dictate")
        dictate.setEnabled(os.name == "nt")
        dictate.setToolTip("Open Windows dictation (Win+H) for this command field.")
        dictate.clicked.connect(self.dictate)
        row.addWidget(dictate)
        row.addStretch()
        self.tray = None
        tray_button = QPushButton("Keep in tray")
        tray_button.clicked.connect(self.keep_in_tray)
        row.addWidget(tray_button)
        self.stop = QPushButton("Stop selected task")
        self.stop.clicked.connect(self.stop_task)
        row.addWidget(self.stop)
        stop_all = QPushButton("Stop all tasks")
        stop_all.clicked.connect(self.stop_all_tasks)
        row.addWidget(stop_all)
        compose.addLayout(row)
        outer.addWidget(bottom)
        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.sample_health)
        if not preview:
            self.timer.start()
        self.command.setFocus()

    def navigate(self, title):
        if title == "Settings":
            dialog = Settings(self.config, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.config = dialog.config
                self.model_label.setText("Model: " + (self.config["model"] or "not selected"))
                self.site_label.setText(self.config["store_url"])
                self.folder_label.setText(self.config["workspace"])
                self.brand.setText(self.config["assistant_name"].upper())
                self.setWindowTitle(self.config["assistant_name"] + " | Strident.AI")
                self.command.setPlaceholderText("Ask " + self.config["assistant_name"] + " or enter a command...")
            self.nav["Settings"].setChecked(False)
            return
        for name, button in self.nav.items():
            button.setChecked(name == title)
        self.pages.setCurrentIndex({"Console": 0, "Task queue": 0, "Files": 1, "Tools": 2, "Store": 3, "Memory": 4, "CurbSentry": 5, "Website": 6}[title])
        if title == "CurbSentry": self.nav["CurbSentry"].setText("CurbSentry")
        if title == "Task queue":
            self.queue_list.setFocus()
            self.tabs.setCurrentIndex(2)
        if title == "Files":
            self.refresh_files()
        if title == "Store":
            self.store_page.refresh()
        if title == "Memory":
            self.memory_page.refresh()

    def submit_input(self):
        text = self.command.text().strip()
        if text:
            self.command.clear()
            self.submit(text)

    def submit(self, text):
        if self.preview:
            return
        if len(text) > 12000:
            QMessageBox.warning(self, "Command too long", "Use a command under 12,000 characters or attach a text file.")
            return
        try:
            self.controller.submit(text, self.config, self.attachment)
            self.navigate("Console")
            self.tabs.setCurrentIndex(0)
        except Exception as exc:
            QMessageBox.warning(self, "Task not queued", str(exc))

    def on_event(self, event):
        task_id = event["id"]
        kind = event["kind"]
        if kind == "queued":
            record = {"command": event["command"], "status": "queued", "reply": "", "evidence": [], "summary": "Waiting to run."}
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, task_id)
            record["item"] = item
            self.records[task_id] = record
            self.queue_list.addItem(item)
            self.queue_list.setCurrentItem(item)
            self.console.appendPlainText(f"\n> {event['command']}\n  Queued [{task_id}]")
        record = self.records.get(task_id)
        if not record:
            return
        if kind == "started":
            record["status"] = "running"
            record["summary"] = "Task is running."
            self.console.appendPlainText(f"\n[{task_id}] Running")
        elif kind == "log":
            self.logs.appendPlainText(f"{time.strftime('%H:%M:%S')} [{task_id}] {event['text']}")
            if event.get("stage"):
                self.console.appendPlainText(f"\n[{task_id}] {event['text']}")
            if event.get("stage") or event.get("progress"):
                record["summary"] = event["text"]
                self.latest.setText(event["text"])
        elif kind == "delta":
            record["reply"] += event["text"]
            cursor = self.console.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText(event["text"])
            self.console.setTextCursor(cursor)
            self.console.ensureCursorVisible()
        elif kind == "tool":
            result = {"tool": event["name"], **event["result"]}
            record["evidence"].append(result)
            self.console.appendPlainText(f"\n[{task_id}] {event['name']}: {result['summary']}")
            formatted = format_tool_result(result)
            if formatted:
                self.console.appendPlainText(formatted)
                record.setdefault("shown_tool_replies", []).append(formatted)
            self.logs.appendPlainText(f"[{task_id}] {json.dumps(result, ensure_ascii=False)}")
        elif kind == "result":
            record["status"] = event["status"]
            record["summary"] = event["summary"]
            record["metrics"] = event.get("metrics", {})
            # Keep already-observed evidence on cancellation or timeout.
            if event.get("evidence"):
                record["evidence"] = event["evidence"]
            if event.get("reply"):
                if not record["reply"] and event["reply"] not in record.get("shown_tool_replies", []):
                    self.console.appendPlainText(event["reply"])
                record["reply"] = event["reply"]
            self.console.appendPlainText(f"\n[{task_id}] {event['status'].replace('_', ' ').upper()}: {event['summary']}\n")
            self.latest.setText(event["summary"])
        record["item"].setText(f"{record['status'].replace('_', ' ').upper()}\n{record['command'][:70]}")
        if self.queue_list.currentItem() == record["item"]:
            self.show_task(record["item"])

    def show_task(self, item, previous=None):
        if not item:
            self.results.clear()
            return
        record = self.records[item.data(Qt.ItemDataRole.UserRole)]
        reply = record["reply"] or "\n\n".join(filter(None, (format_search_results(e) for e in record["evidence"])))
        text = f"{record['command']}\n\nStatus: {record['status']}\n{record['summary']}\n\n{reply}"
        metrics = record.get("metrics", {})
        if metrics:
            text += f"\n\nExecution: {metrics['route']}; {metrics['model_turns']} model turns; {metrics['tool_calls']} tool calls; {metrics['reused_reads']} reused reads; {metrics['execution_seconds']:.3f}s worker time."
        if record["evidence"]:
            text += "\n\nTOOL EVIDENCE\n" + json.dumps(record["evidence"], indent=2, ensure_ascii=False)
        self.results.setPlainText(text)

    def clear_finished(self):
        for task_id, record in list(self.records.items()):
            if record["status"] not in {"queued", "running"}:
                self.queue_list.takeItem(self.queue_list.row(record["item"]))
                self.records.pop(task_id)
                if self.controller:
                    self.controller.forget(task_id)

    def keep_in_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.latest.setText("System tray is unavailable. Keep the window open or minimize it normally.")
            return
        if self.tray is None:
            self.tray = QSystemTrayIcon(self.windowIcon(), self)
            self.tray.setToolTip("Strident.AI is available for tasks")
            menu = QMenu(self)
            restore = QAction("Open Strident", self)
            restore.triggered.connect(self.restore_window)
            quit_action = QAction("Quit Strident", self)
            quit_action.triggered.connect(self.close)
            menu.addAction(restore)
            menu.addAction(quit_action)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(lambda reason: self.restore_window() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        self.tray.show()
        self.hide()

    def restore_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def stop_task(self):
        item = self.queue_list.currentItem()
        if self.controller:
            self.controller.cancel_task(item.data(Qt.ItemDataRole.UserRole) if item else None)

    def stop_all_tasks(self):
        if self.controller:
            self.controller.cancel_all()

    def sample_health(self):
        try:
            cpu = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            text = f"System CPU     {cpu:.1f}%\nSystem memory  {memory.percent:.1f}%"
            if self.process:
                own = self.process.cpu_percent() / (psutil.cpu_count() or 1)
                text += f"\nStrident CPU      {own:.1f}%\nConsole RAM    {self.process.memory_info().rss / 1024**2:.0f} MB"
            else:
                text += "\nConsole process metrics unavailable"
            self.health.setText(text)
        except (psutil.Error, OSError):
            self.health.setText("Resource metrics unavailable on this system.")

    def refresh_files(self):
        self.file_list.clear()
        root = Path(self.config["workspace"])
        if not root.is_dir():
            self.file_list.addItem("Workspace folder does not exist. Choose one in Settings.")
            return
        try:
            for path in sorted(root.iterdir(), key=lambda p: p.name.casefold())[:100]:
                item = QListWidgetItem(("Folder: " if path.is_dir() else "File: ") + path.name)
                item.setData(Qt.ItemDataRole.UserRole, str(path))
                self.file_list.addItem(item)
        except OSError as exc:
            self.file_list.addItem(str(exc))

    def attach_workspace_file(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and Path(path).is_file():
            self.set_attachment(path)
            self.navigate("Console")

    def attach(self):
        path, _ = QFileDialog.getOpenFileName(self, "Attach a text file", self.config["workspace"], "Text and code (*.txt *.md *.py *.js *.json *.csv *.log);;All files (*)")
        if path:
            self.set_attachment(path)

    def set_attachment(self, path):
        self.attachment = path
        self.attach_label.setText(Path(path).name if path else "No file attached")
        self.attach_label.setToolTip(path)

    def dictate(self):
        if os.name != "nt":
            return
        import ctypes
        self.command.setFocus()
        # OS dictation is user initiated; this app never captures microphone audio.
        send = ctypes.windll.user32.keybd_event
        send(0x5B, 0, 0, 0)
        send(0x48, 0, 0, 0)
        send(0x48, 0, 2, 0)
        send(0x5B, 0, 2, 0)

    def closeEvent(self, event):
        if self.store_page.updating:
            QMessageBox.information(self, "Listing update in progress", "Wait for the account response before closing. If the request times out, check Gumroad before retrying.")
            event.ignore()
            return
        self.timer.stop()
        self.curbsentry_page.stop()
        if self.controller:
            self.controller.close()
        if self.tray:
            self.tray.hide()
        os.environ.pop("PCS_GUMROAD_TOKEN", None)
        event.accept()
