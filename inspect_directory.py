"""Read-only inventory. Records names/metadata/hashes, never file contents or secrets."""
from __future__ import annotations
import argparse
import ast
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re

SKIP = {".git", ".venv", "venv", "env", "node_modules", "__pycache__", ".pytest_cache"}
PACKAGES = {".zip", ".7z", ".rar", ".msi", ".whl"}
CODE = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".json", ".toml", ".yaml", ".yml", ".txt", ".md", ".ps1", ".bat", ".cmd"}


def category(path: Path, referenced: set):
    name = path.name
    if name.casefold() in referenced:
        return "Referenced by source", "Keep until the referencing code is migrated."
    if path.suffix.lower() in PACKAGES:
        return "Download or archive candidate", "Move outside the active folder after checking installer/archive references."
    if re.search(r"\(\d+\)(?=\.)", name):
        return "Numbered-copy candidate", "Compare with the normal filename and confirm which version is launched."
    if path.suffix.lower() in {".pyc", ".pyo"}:
        return "Regenerable cache", "Python can recreate this after Strident is closed."
    if name.casefold() in {"strident output.txt", "strident_diagnostic.txt"}:
        return "Troubleshooting output candidate", "Move to a diagnostics folder if it is not read by a script."
    if path.suffix.lower() == ".log":
        return "Log or history", "Retain recent logs for diagnosis; check retention before moving."
    if name.casefold() in {"package.json", "package-lock.json", "turbo.json"}:
        return "Node configuration", "Keep only if a separate JavaScript project requires it."
    if path.suffix.lower() in CODE:
        return "Code or configuration", "Keep. Absence of a static reference does not prove it is unused."
    return "Asset or unclassified", "Keep until runtime usage is checked."


def inventory(root: Path):
    root = root.resolve()
    if not root.is_dir():
        raise NotADirectoryError(str(root))
    paths, excluded, errors = [], [], []
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in list(dirs):
            path = Path(directory) / name
            if name in SKIP or path.is_symlink():
                excluded.append(str(path.relative_to(root)))
                dirs.remove(name)
        for name in files:
            path = Path(directory) / name
            if not path.is_symlink():
                paths.append(path)
    referenced = set()
    imports = defaultdict(list)
    # Only software files are scanned in memory for reference metadata.
    for path in paths:
        if path.suffix.lower() not in {".py", ".js", ".mjs", ".cjs", ".ps1", ".bat", ".cmd"}:
            continue
        try:
            if path.stat().st_size > 2_000_000:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for value in re.findall(r"[\"']([^\"'\r\n]{1,200})[\"']", text):
                referenced.add(Path(value.replace("\\", "/")).name.casefold())
            if path.suffix.lower() == ".py":
                tree = ast.parse(text)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            imports[alias.name.split(".")[0]].append(str(path.relative_to(root)))
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        imports[node.module.split(".")[0]].append(str(path.relative_to(root)))
        except (OSError, SyntaxError) as exc:
            errors.append({"path": str(path.relative_to(root)), "error": type(exc).__name__})
    records = []
    duplicate_map = defaultdict(list)
    for path in sorted(paths):
        try:
            stat = path.stat()
            kind, advice = category(path, referenced)
            record = {"path": str(path.relative_to(root)), "size_bytes": stat.st_size,
                      "modified_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                      "category": kind, "advice": advice}
            # Hash small software files only; no values or excerpts enter the output.
            if path.suffix.lower() in CODE and stat.st_size <= 2_000_000:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                record["sha256"] = digest
                duplicate_map[(digest, stat.st_size)].append(record["path"])
            records.append(record)
        except OSError as exc:
            errors.append({"path": str(path.relative_to(root)), "error": type(exc).__name__})
    return {"project": str(root), "generated_utc": datetime.now(timezone.utc).isoformat(),
            "files": records, "excluded_directories": excluded,
            "exact_duplicate_groups": [group for (_, size), group in duplicate_map.items() if size and len(group) > 1],
            "imported_modules": {k: sorted(set(v)) for k, v in sorted(imports.items())}, "errors": errors}


def report(data):
    rows = ["# Strident folder inventory", "", f"Project: `{data['project']}`", "",
        "This is a read-only inventory. Nothing has been moved or deleted. Static references are incomplete: plugins, imports and runtime paths can make an apparently unreferenced file necessary.", "",
        "## Cleanup candidates", "", "| File | Category | Recommendation |", "|---|---|---|"]
    candidates = [r for r in data["files"] if "candidate" in r["category"] or r["category"] == "Regenerable cache"]
    for item in candidates:
        path = item["path"].replace("|", "\\|")
        rows.append(f"| `{path}` | {item['category']} | {item['advice']} |")
    if not candidates:
        rows.append("| None identified | | No files are approved for deletion. |")
    rows += ["", "## Exact duplicate groups", ""]
    rows += ["- " + ", ".join(f"`{p}`" for p in group) for group in data["exact_duplicate_groups"]]
    if not data["exact_duplicate_groups"]:
        rows.append("No matching nonempty software files found.")
    rows += ["", "## Complete file list", "", "| File | Bytes | Category |", "|---|---:|---|"]
    for item in data["files"]:
        path = item["path"].replace("|", "\\|")
        rows.append(f"| `{path}` | {item['size_bytes']} | {item['category']} |")
    rows += ["", "## Excluded folders", ""] + [f"- `{p}`" for p in data["excluded_directories"]]
    rows += ["", "File contents, credentials, environment variables and log text are not included. Review the filenames before sharing. The JSON companion includes hashes and imported module names for dependency and duplicate analysis.", ""]
    return "\n".join(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output", type=Path, default=Path.home() / "Downloads")
    args = parser.parse_args()
    data = inventory(args.project)
    args.output.mkdir(parents=True, exist_ok=True)
    base = args.output / ("Strident_File_Inventory_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    base.with_suffix(".json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    base.with_suffix(".md").write_text(report(data), encoding="utf-8")
    print("Nothing changed in the project. Reports saved to:")
    print(base.with_suffix(".md"))
    print(base.with_suffix(".json"))


if __name__ == "__main__":
    main()
