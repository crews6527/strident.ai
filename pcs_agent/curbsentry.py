"""Explicit read-only adapter. No Curb imports, camera access or model requests."""
from __future__ import annotations
import http.client
import json
from pathlib import Path
import re
import threading
from urllib.parse import urlsplit

def load_bridge(path):
    path=Path(path)
    if path.suffix.lower()!=".json" or path.stat().st_size>4096:
        raise ValueError("Select CurbSentry's strident-bridge.json (under 4 KiB).")
    data=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data,dict) or data.get("schema_version")!=1:
        raise ValueError("Unsupported CurbSentry connection file.")
    url=urlsplit(data.get("url",""))
    if url.scheme!="http" or url.hostname!="127.0.0.1" or url.path not in {"","/"} or url.username or url.password or url.query or url.fragment:
        raise ValueError("The CurbSentry adapter only connects to this computer's 127.0.0.1 service.")
    port=url.port
    if port is None or not 1024<=port<=65535: raise ValueError("Invalid local CurbSentry port.")
    if not re.fullmatch(r"[a-f0-9]{64}",data.get("token","")):
        raise ValueError("Invalid alert-reader key.")
    return dict(port=port,token=data["token"])

class AlertClient:
    def __init__(self,bridge):
        self.bridge=bridge
        self.lock=threading.Lock()
        self.connection=None
        self.closed=False

    def close(self):
        with self.lock:
            self.closed=True
            connection=self.connection
        if connection:
            if connection.sock:
                import socket
                try: connection.sock.shutdown(socket.SHUT_RDWR)
                except OSError: pass
            connection.close()

    def poll(self):
        connection=http.client.HTTPConnection("127.0.0.1",self.bridge["port"],timeout=2)
        with self.lock:
            if self.closed: raise RuntimeError("CurbSentry monitoring stopped.")
            self.connection=connection
        # A wall-clock deadline also closes a response that trickles bytes slowly.
        deadline=threading.Timer(3,self.close)
        deadline.daemon=True;deadline.start()
        try:
            connection.request("GET","/api/alerts",headers={"Authorization":"Bearer "+self.bridge["token"]})
            response=connection.getresponse()
            raw=response.read(256001)
            if len(raw)>256000: raise ValueError("Alert queue exceeds the adapter's response limit. Review older alerts in CurbSentry.")
            if response.status!=200: raise RuntimeError("CurbSentry rejected the alert-reader connection. Reconnect with its current bridge file.")
            data=json.loads(raw)
            if data.get("schema_version")!=1 or not isinstance(data.get("alerts"),list):
                raise ValueError("Invalid CurbSentry alert response.")
            if len(data["alerts"])>1000: raise ValueError("Too many alerts in one response.")
            for item in data["alerts"]:
                if not isinstance(item,dict) or not re.fullmatch(r"[a-f0-9]{32}",item.get("id","")) or not isinstance(item.get("count"),int) or not isinstance(item.get("capture_iso"),str):
                    raise ValueError("Invalid CurbSentry alert record.")
            return data["alerts"]
        finally:
            deadline.cancel()
            connection.close()
            with self.lock: self.connection=None
