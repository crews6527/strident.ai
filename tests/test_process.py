import json
import multiprocessing
from pathlib import Path
import queue
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pcs_agent.config import validate
from pcs_agent.provider import Ollama
from pcs_agent.runtime import Controller


def slow_worker(pipe, command, config, attachment, history):
    pipe.send({"kind": "log", "stage": True, "text": "worker alive"})
    time.sleep(30)
    pipe.close()


class FakeOllama(BaseHTTPRequestHandler):
    requests = []
    def log_message(self, *args):
        pass
    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.requests.append((self.path, payload))
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        for data in ({"message": {"role": "assistant", "content": "Hello "}, "done": False},
                     {"message": {"role": "assistant", "content": "Tony"}, "done": True}):
            self.wfile.write((json.dumps(data) + "\n").encode())
            self.wfile.flush()


class ProviderTests(unittest.TestCase):
    def test_native_stream_and_resource_options(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            config = validate({"ollama_url": f"http://127.0.0.1:{server.server_port}", "model": "exact:2b", "request_timeout": 5, "num_thread": 2})
            events = []
            message = Ollama(config).chat([{"role": "user", "content": "Hello"}], [], events.append)
            self.assertEqual(message["content"], "Hello Tony")
            path, payload = FakeOllama.requests[-1]
            self.assertEqual(path, "/api/chat")
            self.assertEqual(payload["options"]["num_thread"], 2)
            self.assertEqual(payload["options"]["num_ctx"], 4096)
            self.assertNotIn("extra_body", payload)
            self.assertEqual(sum(e["kind"] == "delta" for e in events), 2)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=1)


class ProcessTests(unittest.TestCase):
    def wait_event(self, events, kind, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            event = events.get(timeout=max(0.1, deadline - time.monotonic()))
            if event["kind"] == kind:
                return event
        self.fail(f"No {kind} event")

    def test_real_spawned_direct_command(self):
        events = queue.Queue()
        controller = Controller(events.put)
        try:
            controller.submit("Help", validate({}))
            result = self.wait_event(events, "result")
            self.assertEqual(result["status"], "complete")
            self.assertTrue(result["evidence"])
        finally:
            controller.close()
        self.assertFalse(controller.thread.is_alive())

    def test_stop_terminates_worker(self):
        events = queue.Queue()
        controller = Controller(events.put, worker=slow_worker)
        try:
            task_id = controller.submit("wait", validate({}))
            self.wait_event(events, "log")
            controller.cancel_task(task_id)
            result = self.wait_event(events, "result")
            self.assertEqual(result["status"], "cancelled")
        finally:
            controller.close()
        self.assertFalse(controller.thread.is_alive())
        self.assertEqual(multiprocessing.active_children(), [])

    def test_queue_cancellation(self):
        events = queue.Queue()
        controller = Controller(events.put, worker=slow_worker)
        try:
            first = controller.submit("one", validate({}))
            self.wait_event(events, "log")
            second = controller.submit("two", validate({}))
            controller.cancel_task(second)
            controller.cancel_task(first)
            results = [self.wait_event(events, "result"), self.wait_event(events, "result")]
            self.assertEqual({e["status"] for e in results}, {"cancelled"})
        finally:
            controller.close()

    def test_deadline_stops_worker(self):
        events = queue.Queue()
        controller = Controller(events.put, worker=slow_worker)
        try:
            controller.submit("wait", validate({"task_timeout": 5}))
            result = self.wait_event(events, "result")
            self.assertEqual(result["status"], "failed")
            self.assertIn("deadline", result["summary"])
            self.assertIn("Last stage: worker alive", result["summary"])
        finally:
            controller.close()
        self.assertEqual(multiprocessing.active_children(), [])

    def test_stop_all_cancels_active_and_waiting_tasks(self):
        events = queue.Queue()
        controller = Controller(events.put, worker=slow_worker)
        try:
            first = controller.submit("one", validate({}))
            self.wait_event(events, "log")
            second = controller.submit("two", validate({}))
            controller.cancel_all()
            results = [self.wait_event(events, "result"), self.wait_event(events, "result")]
            self.assertEqual({event["id"] for event in results}, {first, second})
            self.assertEqual({event["status"] for event in results}, {"cancelled"})
        finally:
            controller.close()
        self.assertEqual(multiprocessing.active_children(), [])


if __name__ == "__main__":
    unittest.main()
