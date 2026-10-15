from __future__ import annotations
import json
import os
from pathlib import Path
from urllib.parse import urlsplit


DEFAULTS = {
    "schema_version": 1,
    "ollama_url": "http://127.0.0.1:11434",
    "model": "",
    "text_model": "",
    "num_ctx": 4096,
    "num_thread": 2,
    "num_predict": 512,
    "request_timeout": 15,
    "model_timeout": 45,
    "task_timeout": 60,  # worker inactivity budget, renewed by real progress
    "max_task_seconds": 900,  # explicit overall ceiling, never renewed
    "preview_port": 8765,
    "preview_key": "",
    "preview_hosts": ["127.0.0.1", "localhost"],
    "keep_alive": "1m",
    "workspace": str(Path.home() / "Documents" / "PromptCopyStudio"),
    "apps": {},
    "instagram_folder": "",
    "store_url": "https://promptcopystudio.42web.io",
    "assistant_name": "Strident",
    "curbsentry_bridge": "",
    "data_dir": str(Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share"))) / "PromptCopyStudioAgent"),
}


def config_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
    return base / "PromptCopyStudioAgent" / "config.json"


def validate(data: dict) -> dict:
    result = DEFAULTS | data
    if result["schema_version"] != 1:
        raise ValueError("Unsupported configuration version.")
    url = urlsplit(result["ollama_url"])
    if url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Ollama must use a local HTTP address (localhost or 127.0.0.1).")
    if url.username or url.password or url.query or url.fragment or url.path not in {"", "/"}:
        raise ValueError("Use an Ollama server address without a path or credentials.")
    _ = url.port  # validates malformed ports
    for key, low, high in (("num_ctx", 1024, 32768), ("num_thread", 1, 32),
                          ("num_predict", 64, 4096), ("request_timeout", 2, 120), ("model_timeout", 2, 120),
                          ("task_timeout", 5, 300), ("max_task_seconds", 5, 3600),
                          ("preview_port", 1024, 65535)):
        if type(result[key]) is not int or not low <= result[key] <= high:
            raise ValueError(f"{key} must be an integer from {low} to {high}.")
    if not isinstance(result['preview_key'], str) or (result['preview_key'] and len(result['preview_key']) < 32):
        raise ValueError('Preview access key must be empty or at least 32 characters.')
    if not isinstance(result['preview_hosts'], list) or not result['preview_hosts'] or any(not isinstance(h,str) or not __import__('re').fullmatch(r'[A-Za-z0-9.-]+',h) for h in result['preview_hosts']):
        raise ValueError('Preview hosts must be exact hostnames without ports or paths.')
    if result["keep_alive"] not in {"0", "30s", "1m", "5m"}:
        raise ValueError("Invalid keep_alive setting.")
    for name in ("model", "text_model"):
        if not isinstance(result[name], str) or len(result[name]) > 150:
            raise ValueError("Invalid model name.")
    if not isinstance(result["apps"], dict):
        raise ValueError("apps must map names to absolute executable paths.")
    for name, path in result["apps"].items():
        if not isinstance(name, str) or not isinstance(path, str) or not Path(path).is_absolute():
            raise ValueError("Each custom app needs a name and an absolute executable path.")
        if Path(path).suffix.lower() not in {".exe", ".com"}:
            raise ValueError("Custom app paths must be executables, not scripts.")
    if not isinstance(result["workspace"], str) or not Path(result["workspace"]).is_absolute():
        raise ValueError("Workspace must be an absolute folder path.")
    if not isinstance(result["instagram_folder"], str):
        raise ValueError("Invalid Instagram content folder.")
    if not isinstance(result["curbsentry_bridge"], str) or (result["curbsentry_bridge"] and not Path(result["curbsentry_bridge"]).is_absolute()):
        raise ValueError("CurbSentry connection file must use an absolute path.")
    if result["instagram_folder"] and not Path(result["instagram_folder"]).is_absolute():
        raise ValueError("Instagram content folder must be absolute.")
    if not isinstance(result["data_dir"], str) or not Path(result["data_dir"]).is_absolute():
        raise ValueError("Data folder must be absolute.")
    if not isinstance(result["assistant_name"], str) or not 1 <= len(result["assistant_name"].strip()) <= 60:
        raise ValueError("Choose an assistant name of 1 to 60 characters.")
    store = urlsplit(result["store_url"])
    if store.scheme not in {"https", "http"} or not store.hostname or store.username or store.password:
        raise ValueError("Use your public HTTP(S) store URL without credentials.")
    return {key: result[key] for key in DEFAULTS}


def load(path: Path | None = None) -> dict:
    path = path or config_path()
    if not path.exists():
        return validate({})
    data = validate(json.loads(path.read_text(encoding="utf-8")))
    if data["assistant_name"] == "Studio":
        data["assistant_name"] = "Strident"
        save(data, path)
    return data


def save(data: dict, path: Path | None = None) -> None:
    data = validate(data)
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    import tempfile
    fd, name = tempfile.mkstemp(prefix='config-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(json.dumps(data, indent=2) + '\n')
        os.chmod(name, 0o600)
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def import_rc1_settings(path, current):
    """Explicit, data-only migration from the separately installed console RC1."""
    path = Path(path)
    if path.suffix.lower() != ".json" or path.stat().st_size > 128000:
        raise ValueError("Choose the RC1 config.json, smaller than 128 KB.")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or data.get("schema_version") != 1 or "ollama_url" not in data:
        raise ValueError("This does not look like the console RC1 configuration. Set the new values manually instead.")
    allowed = {"ollama_url", "model", "num_ctx", "num_thread", "num_predict", "request_timeout", "task_timeout", "keep_alive", "workspace", "apps"}
    return validate(current | {key: data[key] for key in allowed if key in data})
