from __future__ import annotations
from contextlib import contextmanager
import json
import http.client
import socket
import time
import urllib.error
import urllib.request


def nonthinking_value(metadata):
    control = metadata.get("thinking", {})
    if isinstance(control, dict) and isinstance(control.get("values"), list):
        if any(value is False for value in control["values"]):
            return False
    # Older servers report only capabilities, without a values descriptor.
    # An explicit descriptor takes precedence, including level-only controls.
    if "thinking" not in metadata and "thinking" in metadata.get("capabilities", []):
        return False
    return None


class Ollama:
    def __init__(self, config: dict):
        self.config = config
        self.base = config["ollama_url"].rstrip("/")

    @contextmanager
    def _errors(self, path, seconds, phase):
        try:
            yield
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read(2000).decode(errors="replace")
            except (OSError, TimeoutError):
                detail = "The error response could not be read."
            raise RuntimeError(f"Ollama {path} returned HTTP {exc.code}: {detail}") from exc
        except (http.client.RemoteDisconnected, ConnectionResetError, ConnectionAbortedError) as exc:
            raise RuntimeError(
                f"Ollama {path} closed the connection before completing a response while {phase}. "
                "Check the ollama serve window for model-runner errors. "
                "This is a disconnected request, not a confirmed response timeout."
            ) from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise RuntimeError(f"Ollama {path} timed out after {seconds:g}s while {phase}. Run Test-Ollama.cmd to check the selected model directly.") from exc
            raise RuntimeError(f"Cannot connect to Ollama at {self.base} during {path}: {exc.reason}. Open Ollama and refresh models in Settings.") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise RuntimeError(f"Ollama {path} timed out after {seconds:g}s while {phase}. Run Test-Ollama.cmd to check the selected model directly.") from exc

    def _open(self, path, payload=None, timeout=None):
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(self.base + path, data=data,
                                         headers={"Content-Type": "application/json"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        seconds = timeout if timeout is not None else self.config["request_timeout"]
        with self._errors(path, seconds, "waiting for the server response"):
            return opener.open(request, timeout=seconds)

    def json(self, path, payload=None):
        with self._errors(path, self.config["request_timeout"], "reading the server response"):
            with self._open(path, payload) as response:
                data = response.read(1_000_001)
        if len(data) > 1_000_000:
            raise RuntimeError("Ollama response exceeded the allowed size.")
        return json.loads(data)

    def inspect(self, *, include_version=True):
        version = self.json("/api/version") if include_version else {}
        models = self.json("/api/tags").get("models", [])
        return {"version": version.get("version", "unknown"),
                "models": [{"name": m.get("name", ""), "digest": m.get("digest", ""),
                            "size_gb": round(m.get("size", 0) / 1024**3, 2)} for m in models]}

    def chat(self, messages: list, tools: list, emit, *, think=None):
        payload = {"model": self.config["model"], "messages": messages, "stream": True,
                   "keep_alive": self.config["keep_alive"],
                   "options": {"num_ctx": self.config["num_ctx"], "num_thread": self.config["num_thread"],
                               "num_predict": self.config["num_predict"], "temperature": 0.3}}
        if tools:
            payload["tools"] = tools
        if think is not None:
            payload["think"] = think
        emit({"kind": "log", "stage": True,
              "text": f"Ollama request settings: thinking={think if think is not None else 'model default'}; "
                      f"output limit={self.config['num_predict']}; context={self.config['num_ctx']}; streaming=True."})
        message = {"role": "assistant", "content": ""}
        calls = []
        done = False
        total = 0
        reasoning_seen = False
        reasoning = ""
        done_reason = ""
        started = time.monotonic()
        first_frame = None
        last_progress = 0.0
        seconds = self.config.get("model_timeout", 45)
        emit({"kind": "log", "stage": True, "text": f"Requesting {self.config['model']} from Ollama. Model response wait: {seconds}s; worker idle deadline: {self.config['task_timeout']}s; overall ceiling: {self.config.get('max_task_seconds', 900)}s."})
        with self._errors("/api/chat", seconds, "waiting for model output"):
            with self._open("/api/chat", payload, timeout=seconds) as response:
                for raw in response:
                    total += len(raw)
                    if total > 2_000_000:
                        raise RuntimeError("Model output exceeded the allowed size.")
                    if not raw.strip():
                        continue
                    chunk = json.loads(raw)
                    if chunk.get("error"):
                        raise RuntimeError(str(chunk["error"]))
                    now = time.monotonic()
                    if first_frame is None:
                        first_frame = now - started
                    if now - last_progress >= 0.5 or chunk.get('done'):
                        emit({'kind':'model_progress','received_bytes':total,'first_frame_seconds':round(first_frame,3)})
                        last_progress = now
                    part = chunk.get("message", {})
                    reasoning += part.get("thinking", "")
                    if part.get("thinking") and not reasoning_seen:
                        reasoning_seen = True
                        emit({"kind": "log", "stage": True, "text": "Ollama is generating reasoning. Waiting for final answer text."})
                    delta = part.get("content", "")
                    if delta:
                        message["content"] += delta
                        emit({"kind": "delta", "text": delta})
                    for call in part.get("tool_calls", []):
                        calls.append(call)
                    if chunk.get("done"):
                        done = True
                        done_reason = chunk.get("done_reason", "")
                        elapsed = time.monotonic() - started
                        duration = chunk.get('eval_duration',0)/1e9
                        emit({'kind':'log', 'stage':False,
                              'text':f"Generation: {elapsed:.3f}s; first frame {first_frame:.3f}s; load {chunk.get('load_duration',0)/1e9:.3f}s; {chunk.get('eval_count',0)/duration if duration else 0:.2f} tokens/s."})
                        break
        if not done:
            raise RuntimeError("The model stream ended before a completed response.")
        if done_reason == "length":
            message["output_truncated"] = True
        if calls:
            message["tool_calls"] = calls
            if reasoning:
                message["thinking"] = reasoning
        elif not message["content"].strip() and reasoning_seen:
            suffix = " It reached the configured output-token limit." if done_reason == "length" else ""
            raise RuntimeError("Ollama generated reasoning but no final answer." + suffix + " Run Test-Ollama.cmd and review the model's thinking controls before changing models.")
        elif not message["content"].strip():
            raise RuntimeError("Ollama completed without final text or a tool call. Run Test-Ollama.cmd to check the selected model.")
        return message
