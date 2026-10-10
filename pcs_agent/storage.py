"""Transactional personal data. No old project modules are loaded."""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import re
import time
from pathlib import Path
import sqlite3


def utc():
    return datetime.now(timezone.utc).isoformat()


SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
 id INTEGER PRIMARY KEY, role TEXT NOT NULL, content TEXT NOT NULL,
 source TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS facts (
 key TEXT PRIMARY KEY, value TEXT NOT NULL, status TEXT NOT NULL,
 source TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS products (
 id TEXT PRIMARY KEY, title TEXT NOT NULL, asset TEXT NOT NULL DEFAULT '',
 checkout_url TEXT NOT NULL DEFAULT '', expected_pages INTEGER,
 description TEXT NOT NULL DEFAULT '', remote_id TEXT NOT NULL DEFAULT '',
 audit TEXT NOT NULL DEFAULT '{}', updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS drafts (
 id INTEGER PRIMARY KEY, product_id TEXT NOT NULL, channel TEXT NOT NULL,
 content TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS task_log (
 id TEXT PRIMARY KEY, command TEXT NOT NULL, status TEXT NOT NULL,
 summary TEXT NOT NULL, evidence TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS imports (digest TEXT PRIMARY KEY, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS model_metadata (
 endpoint TEXT NOT NULL, model TEXT NOT NULL, digest TEXT NOT NULL,
 payload TEXT NOT NULL, checked REAL NOT NULL, PRIMARY KEY(endpoint,model));
CREATE TABLE IF NOT EXISTS post_records (
 id TEXT PRIMARY KEY, source_folder TEXT NOT NULL, post_id TEXT NOT NULL,
 prepared TEXT NOT NULL DEFAULT '');
"""


class State:
    def __init__(self, folder):
        self.path = Path(folder) / "studio.sqlite3"

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.path, timeout=5)
        con.row_factory = sqlite3.Row
        try:
            con.executescript(SCHEMA)
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def history(self, limit=12):
        with self.connection() as con:
            rows = con.execute("SELECT role,content FROM messages WHERE source='runtime' ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"role": r["role"], "content": r["content"][:3000]} for r in reversed(rows)]

    def append_messages(self, messages):
        with self.connection() as con:
            for m in messages:
                if m.get("role") in {"user", "assistant"} and isinstance(m.get("content"), str):
                    con.execute("INSERT INTO messages(role,content,source,created) VALUES(?,?,?,?)",
                                (m["role"], m["content"][:24000], "runtime", utc()))

    def facts(self):
        with self.connection() as con:
            return [dict(r) for r in con.execute("SELECT * FROM facts ORDER BY key")]

    def fact(self, key, value, *, confirmed=False, source="agent proposal"):
        if not isinstance(key, str) or not 1 <= len(key.strip()) <= 100 or not isinstance(value, str) or not 1 <= len(value.strip()) <= 2000:
            raise ValueError("Memory needs a key under 100 characters and a value under 2,000 characters.")
        with self.connection() as con:
            con.execute("BEGIN IMMEDIATE")
            existing = con.execute("SELECT status FROM facts WHERE key=?", (key.strip(),)).fetchone()
            if existing and existing["status"] == "confirmed" and not confirmed:
                raise PermissionError("A proposal cannot replace confirmed memory. Use an explicit Remember command to change it.")
            con.execute("INSERT INTO facts VALUES(?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,status=excluded.status,source=excluded.source,updated=excluded.updated",
                        (key.strip(), value.strip(), "confirmed" if confirmed else "review", source, utc()))

    def confirm_fact(self, key):
        with self.connection() as con:
            con.execute("UPDATE facts SET status='confirmed',source='user reviewed',updated=? WHERE key=?", (utc(), key))

    def forget(self, key):
        with self.connection() as con:
            changed = con.execute("DELETE FROM facts WHERE key=?", (key,)).rowcount
        return bool(changed)

    def context(self, query="", max_chars=4000):
        parts = []
        used = 0
        words = set(re.findall(r"\w{3,}", query.casefold()))
        facts = self.facts()
        # Prioritize related confirmed facts, preserving deterministic key order on ties.
        facts.sort(key=lambda f: -len(words & set(re.findall(r"\w{3,}", (f["key"] + " " + f["value"]).casefold()))))
        for f in facts:
            if f["status"] != "confirmed":
                continue
            line = json.dumps({"key": f["key"], "value": f["value"]}, ensure_ascii=False)
            if used + len(line) + 1 > max_chars:
                continue
            parts.append(line)
            used += len(line)
        return "\n".join(parts)

    def model_metadata(self, endpoint, model, digest, *, now=None):
        if not isinstance(digest, str) or not digest:
            return None
        now = time.time() if now is None else now
        with self.connection() as con:
            row = con.execute("SELECT digest,payload,checked FROM model_metadata WHERE endpoint=? AND model=?",
                              (endpoint, model)).fetchone()
        if not row or row["digest"] != digest or not 0 <= now - row["checked"] <= 300:
            return None
        try:
            data = json.loads(row["payload"])
            if isinstance(data, dict) and isinstance(data.get("capabilities"), list):
                return data
        except (ValueError, TypeError):
            pass
        return None

    def save_model_metadata(self, endpoint, model, digest, metadata, *, now=None):
        if not isinstance(digest, str) or not digest:
            return
        # Store controls only, never model prompts, weights or customer content.
        data = {"capabilities": metadata.get("capabilities", []), "thinking": metadata.get("thinking", {})}
        if not isinstance(data["capabilities"], list):
            return
        with self.connection() as con:
            con.execute("INSERT OR REPLACE INTO model_metadata VALUES(?,?,?,?,?)",
                        (endpoint, model, digest, json.dumps(data), time.time() if now is None else now))

    def record_task(self, task_id, command, result):
        evidence = result.get("evidence", [])
        serialized = json.dumps(evidence, ensure_ascii=False)
        if len(serialized) > 64000:
            serialized = json.dumps({"truncated": True, "preview": serialized[:60000]}, ensure_ascii=False)
        with self.connection() as con:
            con.execute("INSERT OR REPLACE INTO task_log VALUES(?,?,?,?,?,?)", (task_id, command[:12000],
                result["status"], result["summary"][:4000], serialized, utc()))

    def archived_history(self, limit=200):
        with self.connection() as con:
            rows = con.execute("SELECT role,content FROM messages WHERE source='legacy archive' ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in reversed(rows)]

    def search_result(self, task_id=""):
        """Retrieve successful search evidence without another network or model call."""
        with self.connection() as con:
            sql = "SELECT id,evidence FROM task_log"
            args = ()
            if task_id:
                sql += " WHERE id=?"
                args = (task_id,)
            for row in con.execute(sql + " ORDER BY updated DESC", args):
                evidence = json.loads(row["evidence"])
                if not isinstance(evidence, list):
                    continue
                for result in reversed(evidence):
                    if isinstance(result, dict) and result.get("tool") == "search_web" and result.get("ok") is True and result.get("results"):
                        return row["id"], result
        return None

    def tool_result(self, names):
        with self.connection() as con:
            for row in con.execute("SELECT id,evidence FROM task_log ORDER BY updated DESC LIMIT 200"):
                try:
                    evidence = json.loads(row["evidence"])
                except ValueError:
                    continue
                if not isinstance(evidence, list):
                    continue
                for result in reversed(evidence):
                    if isinstance(result, dict) and result.get("tool") in names:
                        return row["id"], result
        return None

    def products(self):
        with self.connection() as con:
            return [dict(r) for r in con.execute("SELECT * FROM products ORDER BY title")]

    def product(self, product_id):
        with self.connection() as con:
            row = con.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not row:
            raise ValueError("Unknown product. Add or select it on the Store page first.")
        return dict(row)

    def upsert_product(self, product):
        fields = ("id", "title", "asset", "checkout_url", "expected_pages", "description", "remote_id")
        values = [product.get(f, "") for f in fields]
        with self.connection() as con:
            con.execute("INSERT INTO products(id,title,asset,checkout_url,expected_pages,description,remote_id,updated) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,asset=excluded.asset,checkout_url=excluded.checkout_url,expected_pages=excluded.expected_pages,description=excluded.description,remote_id=excluded.remote_id,audit='{}',updated=excluded.updated", (*values, utc()))

    def save_audit(self, product_id, audit):
        with self.connection() as con:
            con.execute("UPDATE products SET audit=?,updated=? WHERE id=?", (json.dumps(audit), utc(), product_id))

    def draft(self, product_id, channel, content):
        if channel not in {"listing", "instagram", "website"} or not isinstance(content, str) or not 1 <= len(content.strip()) <= 12000:
            raise ValueError("Use listing, instagram or website and 1 to 12,000 characters of draft text.")
        self.product(product_id)
        with self.connection() as con:
            cursor = con.execute("INSERT INTO drafts(product_id,channel,content,created) VALUES(?,?,?,?)", (product_id, channel, content.strip(), utc()))
            return cursor.lastrowid

    def drafts(self, product_id):
        with self.connection() as con:
            return [dict(r) for r in con.execute("SELECT * FROM drafts WHERE product_id=? ORDER BY id DESC LIMIT 20", (product_id,))]

    def import_personal_data(self, history_path=None, memory_path=None):
        """Read JSON only; duplicate input bytes are not imported twice."""
        import hashlib
        counts = {"messages": 0, "facts": 0, "already_imported": 0}
        for path, kind in ((history_path, "history"), (memory_path, "memory")):
            if not path:
                continue
            path = Path(path)
            if path.suffix.lower() != ".json" or path.stat().st_size > 2_000_000:
                raise ValueError("Choose a JSON data file smaller than 2 MB.")
            raw = path.read_bytes()
            data = json.loads(raw.decode("utf-8-sig"))
            digest = kind + ":" + hashlib.sha256(raw).hexdigest()
            messages, facts = [], []
            if kind == "history":
                if not isinstance(data, list) or len(data) > 10000:
                    raise ValueError("History must be a list of at most 10,000 messages.")
                for item in data:
                    if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"} or not isinstance(item.get("content"), str):
                        raise ValueError("Invalid conversation record; no records from this file were imported.")
                    messages.append((item["role"], item["content"][:24000], "legacy archive", utc()))
            else:
                if not isinstance(data, dict):
                    raise ValueError("Long-term memory must be an object.")
                for section, items in data.items():
                    if not isinstance(items, dict):
                        raise ValueError("Memory sections must be objects.")
                    for key, value in items.items():
                        if not isinstance(value, dict) or not isinstance(value.get("value"), str):
                            raise ValueError("Memory entries must have a text value.")
                        label = str(section) + "." + str(key)
                        if len(label) > 100 or len(value["value"]) > 2000:
                            raise ValueError("Memory entry exceeds the import limit.")
                        facts.append((label, value["value"], "review", "legacy archive", utc()))
            with self.connection() as con:
                if con.execute("SELECT 1 FROM imports WHERE digest=?", (digest,)).fetchone():
                    counts["already_imported"] += 1
                    continue
                con.executemany("INSERT INTO messages(role,content,source,created) VALUES(?,?,?,?)", messages)
                for fact in facts:
                    counts["facts"] += con.execute("INSERT OR IGNORE INTO facts VALUES(?,?,?,?,?)", fact).rowcount
                con.execute("INSERT INTO imports VALUES(?,?)", (digest, utc()))
                counts["messages"] += len(messages)
        return counts
