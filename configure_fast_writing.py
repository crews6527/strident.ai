"""Explicit setup command. Test a small installed model before selecting it."""
from __future__ import annotations
import json
import multiprocessing as mp
from pathlib import Path
import shutil
from datetime import datetime
from pcs_agent.config import load, config_path, save
from pcs_agent.provider import Ollama
from diagnose_ollama import run_check


def configure(config, *, client=None, checker=run_check, save_config=save, emit=print):
    if config.get("text_model"):
        emit("Writing model already selected: " + config["text_model"] + ". No settings changed. Test it in Settings if needed.")
        return True
    emit("Checking installed models; no models will be downloaded.")
    info = (client or Ollama(config)).inspect()
    candidates = sorted({m["name"]: m for m in info["models"]
                         if 0 < m.get("size_gb", 0) <= 1.5}.values(), key=lambda m: (m["size_gb"], m["name"]))
    if not candidates:
        emit("No installed model under 1.5 GB was found. No settings changed. Website checks still work without a model.")
        return False
    # At most two small models, no automatic model downloads or repeated retries.
    for item in candidates[:2]:
        name = item["name"]
        emit("Testing installed writing model: " + name)
        result = checker({**config, "model": name, "num_ctx": min(config["num_ctx"], 2048),
                          "num_predict": 64}, emit=emit)
        if result["ok"]:
            save_config({**config, "text_model": name})
            emit(f"PASS: {name} replied in {result.get('elapsed', '?')}s. It is now the writing model. Task model remains {config['model'] or 'unselected'}.")
            return True
        emit("FAILED: " + result.get("error", "No completed reply."))
    emit("No tested small model replied successfully. No settings changed. Use the Website page for model-free checks.")
    return False


def main():
    try:
        config = load()
        path = config_path()
        backup = None
        def persist(values):
            nonlocal backup
            if path.exists():
                backup = path.with_name("config-before-writing-" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".json")
                shutil.copy2(path, backup)
            save(values, path)
        okay = configure(config, save_config=persist)
        if backup:
            print("Settings backup: " + str(backup))
        return 0 if okay else 1
    except Exception as exc:
        print("SETUP FAILED: " + str(exc))
        return 1


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
