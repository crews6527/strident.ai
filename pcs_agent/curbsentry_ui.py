from __future__ import annotations
import json
import os
from pathlib import Path
import tempfile
import threading
from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QFileDialog,QPlainTextEdit
from .config import save
from .curbsentry import load_bridge,AlertClient

class Events(QObject):
    result=pyqtSignal(dict)

class CurbSentryPage(QWidget):
    def __init__(self,window):
        super().__init__()
        self.window=window
        self.events=Events(self)
        self.events.result.connect(self.received)
        self.thread=None
        self.client=None
        self.running=False
        self.generation=0
        self.seen_path=Path(window.config["data_dir"])/"curbsentry-seen.json"
        self.seen=set()
        if self.seen_path.exists():
            try:
                raw=json.loads(self.seen_path.read_text())
                if isinstance(raw,list):self.seen={x for x in raw if isinstance(x,str)}
            except (ValueError,OSError):pass
        layout=QVBoxLayout(self)
        title=QLabel("CurbSentry alerts")
        title.setObjectName("title");layout.addWidget(title)
        hint=QLabel("Read confirmed repeat-sighting alerts from CurbSentry on this computer. Monitoring starts only when you choose Start monitoring. Clips and OCR stay in CurbSentry.")
        hint.setWordWrap(True);layout.addWidget(hint)
        controls=QHBoxLayout()
        self.connect_button=QPushButton("Connect...")
        self.connect_button.clicked.connect(self.connect_file);controls.addWidget(self.connect_button)
        self.start_button=QPushButton("Start monitoring")
        self.start_button.clicked.connect(self.toggle);controls.addWidget(self.start_button)
        layout.addLayout(controls)
        self.status=QLabel("Monitoring is off. Select CurbSentry's strident-bridge.json to connect.")
        self.status.setWordWrap(True);layout.addWidget(self.status)
        self.display=QPlainTextEdit();self.display.setReadOnly(True)
        self.display.setPlaceholderText("Confirmed repeat-sighting alerts appear here. Open CurbSentry to review footage or mark an alert reviewed.")
        layout.addWidget(self.display,1)
        self.timer=QTimer(self);self.timer.setInterval(15000);self.timer.timeout.connect(self.poll)

    def connect_file(self):
        default=Path(os.environ.get("LOCALAPPDATA",str(Path.home()/".local/share")))/"CurbSentryPrivate"
        path,_=QFileDialog.getOpenFileName(self,"Choose CurbSentry's read-only connection file",str(default),"JSON files (*.json)")
        if not path:return
        try:
            load_bridge(path)
            self.stop()
            config=self.window.config|{"curbsentry_bridge":path}
            save(config);self.window.config=config
            self.status.setText("Connection file saved. Start CurbSentry, then choose Start monitoring.")
        except Exception as exc:self.status.setText(str(exc))

    def toggle(self):
        if self.running:self.stop();return
        try:load_bridge(self.window.config.get("curbsentry_bridge",""))
        except Exception as exc:self.status.setText("Connect to CurbSentry first. "+str(exc));return
        self.generation+=1;self.running=True
        self.start_button.setText("Stop monitoring");self.connect_button.setEnabled(False)
        self.timer.start();self.poll()

    def poll(self):
        if not self.running or (self.thread and self.thread.is_alive()):return
        generation=self.generation
        try:self.client=AlertClient(load_bridge(self.window.config["curbsentry_bridge"]))
        except Exception as exc:self.status.setText(str(exc));return
        client=self.client
        self.status.setText("Checking CurbSentry's alert queue...")
        def work():
            try:result=dict(alerts=client.poll(),generation=generation)
            except Exception as exc:result=dict(error=str(exc),generation=generation)
            self.events.result.emit(result)
        self.thread=threading.Thread(target=work,name="CurbSentry alert read",daemon=True);self.thread.start()

    def received(self,result):
        if not self.running or result["generation"]!=self.generation:return
        if "error" in result:self.status.setText("CurbSentry unavailable: "+result["error"]);return
        alerts=result["alerts"]
        lines=[];new=[]
        for a in alerts:
            name=a.get("plate") or a.get("label") or " ".join(str(v) for v in a.get("description",{}).values() if v) or "Unidentified vehicle"
            line=f"{name}: {a['count']} sightings within {a.get('window_hours','?')} hours\nCaptured: {a['capture_iso']}\nCameras: {', '.join(a.get('cameras',[]))}\nStatus: {'reviewed' if a.get('acknowledged') else 'needs review'}\nAlert ID: {a['id']}"
            lines.append(line)
            if not a.get("acknowledged") and a["id"] not in self.seen:new.append((a["id"],name))
        self.display.setPlainText("\n\n".join(lines) or "No confirmed repeat-sighting alerts.")
        if new:
            self.seen.update(aid for aid,_ in new)
            try:
                self.seen_path.parent.mkdir(parents=True,exist_ok=True)
                temporary=self.seen_path.with_suffix(".tmp")
                temporary.write_text(json.dumps(sorted(self.seen))+"\n");temporary.replace(self.seen_path)
            except OSError:
                self.status.setText("Alerts received, but notification history could not be saved. Check the data folder.")
                return
            summary="CurbSentry: "+str(len(new))+" new repeat-sighting alert(s). Open CurbSentry to review."
            self.window.console.appendPlainText("\n"+summary)
            self.window.latest.setText(summary)
            self.window.nav["CurbSentry"].setText("CurbSentry · "+str(len(new))+" new")
            from PyQt6.QtWidgets import QApplication
            QApplication.alert(self.window,5000)
        self.status.setText(f"Connected. {len(alerts)} active alert(s). Checking every 15 seconds. No model inference.")

    def stop(self):
        self.running=False;self.generation+=1;self.timer.stop()
        if self.client:self.client.close()
        if self.thread and self.thread.is_alive():self.thread.join(timeout=4)
        self.start_button.setText("Start monitoring");self.connect_button.setEnabled(True)
        self.status.setText("Monitoring stopped. CurbSentry's records are retained.")
