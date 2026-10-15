"""Task planning and bounded reuse. No background work or model-weight changes."""
from __future__ import annotations
import copy
import json
import re
from .tools import direct_command


READ_ONLY = {"help", "search_web", "show_search_results", "read_web", "check_web",
             "store_website", "list_files", "read_file", "instagram_queue",
             "store_products", "memory_list", "website_audit", "website_links"}
SIDE_EFFECTS = {"open_app", "open_url", "instagram_prepare", "store_audit",
                "store_export_listing", "store_save_draft", "gumroad_products",
                "memory_save", "memory_forget", "website_report", "open_store"}


def tool_names(command):
    """Small tool menus for known domains; full menu for unknown action tasks."""
    text = command.casefold()
    for _ in range(3):
        text = re.sub(r"^(?:strident(?:\.ai)?[, ]+|please\s+|(?:can|could|would|will) you\s+)", "", text.strip())
    if text.startswith(("write a short product listing using only these", "write practical website improvements using only this")):
        return set()
    names = set()
    if re.search(r"\b(?:website|webpage|site|https?|domain|url|internet|web)\b", text):
        names.update({"read_web", "website_audit", "website_links", "open_url", "store_website", "website_report"})
    if re.search(r"\b(?:search|news|look up|find online)\b", text):
        names.update({"search_web", "read_web", "show_search_results"})
    if re.search(r"\b(?:product|products|listing|listings|gumroad|store|store_products|store_audit|store_save_draft)\b", text):
        names.update({"store_products", "store_audit", "store_save_draft", "store_export_listing", "gumroad_products", "store_website"})
    if re.search(r"\b(?:memory|remember|preferences|saved|forget)\b", text):
        names.update({"memory_list", "memory_save"})
    if re.search(r"\b(?:file|files|folder|workspace|attachment|attached)\b", text):
        names.update({"list_files", "read_file"})
    if "instagram" in text:
        names.update({"instagram_queue", "instagram_prepare"})
    if re.search(r"\b(?:open|launch|start|run|calculator|notepad)\b", text):
        names.update({"open_app", "open_url"})
    if re.search(r"\b(?:cpu|ram|system health|memory usage)\b", text):
        names.add("system_health")
    if names:
        return names
    if re.fullmatch(r"(?:hello|hi|hey|good (?:morning|evening|afternoon))(?:\s+strident(?:\.ai)?)?[.!?]*", text.strip()) or re.match(r"^(?:write|draft|rewrite|explain|summarize|translate|what is|how do)\b", text):
        return set()
    if re.fullmatch(r"(?:how are you|what(?:'s| is) your name|thanks|thank you)[.!?]*", text.strip()):
        return set()
    return None


def direct_plan(command):
    """Execute all recognized steps, or leave the entire request to the model.

    Remember values, URL punctuation and quoted text are kept intact. Natural
    language 'and' requests remain with the model to avoid splitting data.
    """
    text = command.strip()
    for _ in range(4):
        text = re.sub(r"^(?:Strident(?:\.AI)?[,]\s*|please\s+|(?:can|could|would|will) you\s+)", "", text, flags=re.I)
    if re.match(r"^(?:Remember|/remember)\s+", text, re.I) or (not re.search(r"\s", text) and direct_command(text) and direct_command(text)[0] == "read_web"):
        direct = direct_command(text)
        return [direct] if direct else None
    # Quoted separators are data. The model handles these requests as a whole.
    if re.search(r"[\"']", text) and re.search(r";|\n|\bthen\b", text, re.I):
        return None
    parts = re.split(r"\s*;\s*|\s*\n\s*|\s+(?:and\s+)?then\s+", text, flags=re.I)
    if len(parts) == 1 and re.search(r"\s+and\s+", text, re.I) and not re.search(r"[\"']", text):
        candidates = re.split(r"\s+and\s+", text, flags=re.I)
        if all(direct_command(p) for p in candidates):
            parts = candidates
    if len(parts) > 6 or any(not p.strip() for p in parts):
        return None
    steps = []
    for part in parts:
        part = re.sub(r"^(?:\d+[.)]|[-*])\s+", "", part.strip())
        direct = direct_command(part)
        if not direct:
            return None
        steps.append(direct)
    return steps


def recent_history(history, budget):
    """Keep recent complete user/assistant pairs; never cut a task mid-sentence."""
    selected = []
    used = 0
    pairs = []
    for item in history[-12:]:
        if item.get("role") == "user":
            pairs.append([item])
        elif item.get("role") == "assistant" and pairs and len(pairs[-1]) == 1:
            pairs[-1].append(item)
    for pair in reversed(pairs):
        size = sum(len(str(m.get("content", ""))) for m in pair)
        if len(pair) != 2 or used + size > budget:
            continue
        selected[0:0] = pair
        used += size
    return selected


class TaskTools:
    """Reuse reads only inside this task. Writes invalidate cached reads."""
    def __init__(self, runner, command, metrics):
        self.runner, self.metrics = runner, metrics
        self.refresh = bool(re.search(r"\b(?:again|repeat|refresh|twice|retry|watch|monitor|fresh|live|latest)\b", command, re.I))
        self.repeat_actions = bool(re.search(r"\b(?:again|repeat|twice)\b", command, re.I))
        if re.search(r"\b(?:not|never|avoid|without|no|don't|don’t)\b.{0,80}\b(?:again|repeat|twice)\b", command, re.I | re.S):
            self.repeat_actions = False
        self.cache, self.successful_writes, self.failures = {}, set(), {}

    def run(self, name, arguments):
        key = (name, json.dumps(arguments, sort_keys=True, ensure_ascii=False))
        if not self.refresh and name in READ_ONLY and key in self.cache:
            self.metrics["reused_reads"] += 1
            return {**copy.deepcopy(self.cache[key]), "reused": True,
                    "freshness": "Reused evidence from earlier in this task; no new check was made."}, False
        if not self.repeat_actions and name in SIDE_EFFECTS and key in self.successful_writes:
            return {"ok": False, "summary": "This identical action already succeeded in this task. It was not repeated. Use a new explicit repeat request if needed."}, False
        if self.failures.get(key, 0) >= 2:
            return {"ok": False, "summary": "The same tool arguments failed twice. Change the arguments or explain the blocker instead of retrying."}, False
        self.metrics["tool_calls"] += 1
        # Clear before a write: even a failed call may have partially changed data.
        if name in SIDE_EFFECTS:
            self.cache.clear()
        try:
            result = self.runner.run(name, arguments)
        except Exception as exc:
            result = {"ok": False, "summary": str(exc)}
        if result.get("ok") is True:
            if name in READ_ONLY:
                self.cache[key] = copy.deepcopy(result)
            if name in SIDE_EFFECTS:
                self.successful_writes.add(key)
        else:
            self.failures[key] = self.failures.get(key, 0) + 1
        return result, True
