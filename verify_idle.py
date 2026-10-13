"""Measure the Qt console with isolated data and blocked Ollama requests."""
import argparse
import json
import os
from pathlib import Path
import time
from datetime import datetime, timezone
import tempfile
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--output", type=Path, default=Path.home() / "Downloads" / "Strident_Idle_Result.json")
    args = parser.parse_args()
    if not 5 <= args.seconds <= 60:
        parser.error("Use 5 to 60 seconds.")
    from PyQt6.QtCore import QTimer, Qt
    from PyQt6.QtWidgets import QApplication
    from pcs_agent.config import load
    from pcs_agent.provider import Ollama
    from pcs_agent.ui import ConsoleWindow
    import psutil
    requests = []

    def block_request(path, *unused_args, **unused_kwargs):
        requests.append(str(path))
        raise RuntimeError("Ollama access is blocked during the idle check.")

    with tempfile.TemporaryDirectory(prefix="strident-idle-") as data:
        with patch.dict(os.environ, {"LOCALAPPDATA": data}), patch.object(Ollama, "_open", side_effect=block_request):
            app = QApplication([])
            config = load()
            # Defaults may have been imported before LOCALAPPDATA was isolated.
            config["data_dir"] = str(Path(data) / "PromptCopyStudioAgent")
            config["workspace"] = str(Path(data) / "workspace")
            Path(config["workspace"]).mkdir()
            window = ConsoleWindow(config)
            try:
                window.show()
                app.processEvents()
                started_wall = time.monotonic()
                started_cpu = time.process_time()
                # Coarse timers can fire early and invalidate a complete sample.
                QTimer.singleShot(args.seconds * 1000, Qt.TimerType.PreciseTimer, app.quit)
                app.exec()
                cpu = time.process_time() - started_cpu
                elapsed = time.monotonic() - started_wall
                submitted = len(window.records)
            finally:
                window.close()
                app.processEvents()
    result = {"generated_utc": datetime.now(timezone.utc).isoformat(),
              "elapsed_seconds": round(elapsed, 3), "console_cpu_seconds": round(cpu, 6),
              "console_cpu_percent_one_core": round(100 * cpu / elapsed, 3),
              "console_cpu_percent_machine": round(100 * cpu / elapsed / (psutil.cpu_count() or 1), 3),
              "logical_cores": psutil.cpu_count(), "tasks_submitted": submitted,
              "ollama_requests_attempted": len(requests),
              "inference_requests_attempted": requests.count("/api/chat"),
              "ollama_access": "blocked and counted in this console process",
              "microphone_capture": "not instrumented by this diagnostic",
              "data_isolated": True,
              "completed_sample": elapsed >= args.seconds - 0.25,
              "scope": "this Qt console process only; excludes Ollama and other applications"}
    result["ok"] = result["completed_sample"] and submitted == 0 and not requests
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"Saved: {args.output}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
