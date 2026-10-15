"""Bounded, direct check of the selected local model. Does not change settings."""
from __future__ import annotations
import json
import multiprocessing as mp
from pathlib import Path
import time
from pcs_agent.config import config_path, validate
from pcs_agent.provider import Ollama, nonthinking_value


def check_worker(pipe, config):
    def event(value):
        pipe.send(value)
    started = time.monotonic()
    try:
        client = Ollama(config)
        event({"kind": "log", "text": "Checking Ollama version and installed models..."})
        info = client.inspect()
        event({"kind": "log", "text": "Ollama version: " + str(info["version"])})
        names = [model["name"] for model in info["models"]]
        event({"kind": "log", "text": "Installed models: " + ", ".join(names)})
        if config["model"] not in names:
            raise RuntimeError("The selected exact model tag is not installed. Refresh models in Settings; no other model was substituted.")
        event({"kind": "log", "text": "Reading metadata for " + config["model"]})
        metadata = client.json("/api/show", {"model": config["model"]})
        think = nonthinking_value(metadata)
        event({"kind": "log", "text": "Thinking: " + ("off, supported by reported controls" if think is False else "model default; disabling is not advertised")})
        # A short text-only test with no agent tools or personal memory.
        test_config = {**config, "num_predict": 64, "num_ctx": min(config["num_ctx"], 2048)}
        response = Ollama(test_config).chat([{"role": "user", "content": "Reply with just: Hello."}], [], event, think=think)
        reply = response.get("content", "").strip()
        if response.get("output_truncated"):
            raise RuntimeError("The model probe hit its output-token limit; a complete short reply was not verified.")
        if not reply:
            raise RuntimeError("The text-only model check completed without an answer.")
        event({"kind": "result", "ok": True, "reply": reply[:500], "elapsed": round(time.monotonic() - started, 3)})
    except Exception as exc:
        event({"kind": "result", "ok": False, "error": str(exc), "elapsed": round(time.monotonic() - started, 3)})
    finally:
        pipe.close()


def run_check(config, emit=print, *, worker=check_worker, timeout=None):
    limit = timeout if timeout is not None else config["task_timeout"]
    context = mp.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=worker, args=(sender, config), daemon=True)
    started = time.monotonic()
    last_stage = "starting the model check"
    last_activity = started
    overall = timeout if timeout is not None else config.get("max_task_seconds", 900)
    try:
        process.start()
        sender.close()
        while time.monotonic() - started < overall and time.monotonic() - last_activity < limit:
            if receiver.poll(0.05):
                try:
                    value = receiver.recv()
                except EOFError:
                    break
                if value["kind"] in {"log", "delta", "model_progress"}:
                    last_activity = time.monotonic()
                if value["kind"] == "result":
                    return value
                if value["kind"] == "log":
                    last_stage = value["text"]
                    emit(last_stage)
            elif not process.is_alive():
                break
        return {"kind": "result", "ok": False, "error": f"The whole check reached its {limit:g}s deadline or ended without a result. Last stage: {last_stage}"}
    finally:
        if process.pid:
            process.join(timeout=0.1)
            if process.is_alive():
                process.terminate()
                process.join(timeout=0.5)
            if process.is_alive():
                process.kill()
                process.join(timeout=0.5)
        receiver.close()
        sender.close()


def main():
    try:
        path = config_path()
        if path.exists() and path.stat().st_size > 128000:
            raise ValueError("Settings file is too large to read.")
        values = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        config = validate(values)
        if not config["model"]:
            raise ValueError("Choose and save an installed model in Strident Settings first.")
        print("Address: " + config["ollama_url"])
        print("Selected model: " + config["model"])
        print(f"Metadata wait: {config['request_timeout']}s; model socket wait: {config['model_timeout']}s; worker idle limit: {config['task_timeout']}s; overall ceiling: {config.get('max_task_seconds', 900)}s")
        result = run_check(config)
        if result["ok"]:
            print("PASS: " + result["reply"])
            print(f"Model check completed in {result['elapsed']}s.")
            return 0
        print("FAILED: " + result["error"])
        return 1
    except (OSError, ValueError, TypeError) as exc:
        print("FAILED: " + str(exc))
        return 1


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
