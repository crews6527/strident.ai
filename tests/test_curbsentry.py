import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
from pcs_agent.curbsentry import AlertClient,load_bridge
from pcs_agent.config import validate
from PyQt6.QtWidgets import QApplication
from pcs_agent.ui import ConsoleWindow

class AdapterTests(unittest.TestCase):
    def test_only_explicit_loopback_bridge(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"strident-bridge.json"
            for url in ("http://example.com:8766","http://localhost:8766","https://127.0.0.1:8766","http://user:pw@127.0.0.1:8766","http://127.0.0.1:8766/path"):
                path.write_text(json.dumps(dict(schema_version=1,url=url,token="a"*64)))
                with self.assertRaises(ValueError):load_bridge(path)
            path.write_text(json.dumps(dict(schema_version=1,url="http://127.0.0.1:8766",token="a"*64)))
            self.assertEqual(load_bridge(path)["port"],8766)
    def test_read_queue_and_close(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                assert self.path=="/api/alerts"
                assert self.headers.get("Authorization")=="Bearer "+"a"*64
                body=json.dumps(dict(schema_version=1,alerts=[])).encode()
                self.send_response(200);self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            client=AlertClient(dict(port=server.server_address[1],token="a"*64));self.assertEqual(client.poll(),[])
            client.close()
            with self.assertRaises(RuntimeError):client.poll()
        finally:server.shutdown();server.server_close();thread.join()
    def test_ui_monitor_off_and_notification_dedup(self):
        app=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            w=ConsoleWindow(validate(dict(data_dir=folder)),preview=True)
            page=w.curbsentry_page
            self.assertFalse(page.running);self.assertFalse(page.timer.isActive())
            self.assertIsNone(page.thread)
            page.running=True;page.generation=1
            alert=dict(id="a"*32,count=3,capture_iso="2026-09-12T15:00:00-05:00",plate="TEST428",window_hours=2,cameras=["Front door"],acknowledged=False)
            with patch("pcs_agent.runtime.Ollama") as model:
                page.received(dict(generation=1,alerts=[alert]));page.received(dict(generation=1,alerts=[alert]))
                model.assert_not_called()
            self.assertEqual(w.console.toPlainText().count("new repeat-sighting alert(s)"),1)
            self.assertIn("TEST428",page.display.toPlainText());w.close()
            w2=ConsoleWindow(validate(dict(data_dir=folder)),preview=True)
            self.assertIn("a"*32,w2.curbsentry_page.seen);w2.close()

if __name__=="__main__":unittest.main()
