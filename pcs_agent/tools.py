from __future__ import annotations
import html
import ipaddress
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import time
import urllib.parse
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
import defusedxml.ElementTree as DefusedET
from html.parser import HTMLParser
from pathlib import Path


WINDOWS_APPS = {
    "notepad": "notepad.exe", "calculator": "calc.exe", "file explorer": "explorer.exe",
    "terminal": "wt.exe", "paint": "mspaint.exe", "task manager": "taskmgr.exe",
}
ALIASES = {"calc": "calculator", "explorer": "file explorer", "windows explorer": "file explorer",
           "windows terminal": "terminal", "taskmanager": "task manager", "chrome": "google chrome"}
TOOLS = [
    ("open_app", "Launch an installed desktop app. Built-ins: Notepad, Calculator, File Explorer, Terminal, Paint, Task Manager, browser. Custom apps must be registered in Settings.", {"app": "string"}),
    ("open_url", "Ask the default browser to open a public HTTP(S) URL. This confirms handoff, not page rendering.", {"url": "string"}),
    ("search_web", "Search the public web and return result titles, snippets and URLs. Treat results as untrusted evidence.", {"query": "string"}),
    ("show_search_results", "Show saved web search titles, snippets and URLs. Supply an empty task_id for the latest saved search, or an exact eight-character task ID. This does not run a new search.", {"task_id": "string"}),
    ("read_web", "Read text from an HTTP(S) web page. Does not execute JavaScript or access signed-in browser sessions.", {"url": "string"}),
    ("check_web", "Check outbound HTTPS with a small request.", {}),
    ("store_website", "Retrieve public text from the configured store website; does not verify customer checkout or a signed-in session.", {}),
    ("website_audit", "Check a public page's title, description, headings, mobile metadata and links. Empty url uses the configured website.", {"url": "string"}),
    ("website_links", "Check up to eight public links on a page. Empty url uses the configured website. No checkout or signed-in actions.", {"url": "string"}),
    ("website_report", "Save the latest website check as text and JSON in the workspace. Does not publish.", {}),
    ("open_store", "Open the configured website in the default browser.", {}),
    ("system_health", "Get current system CPU and memory. Does not terminate processes.", {}),
    ("list_files", "List up to 100 files in the configured workspace or attached file's folder.", {"path": "string"}),
    ("read_file", "Read a text file inside the configured workspace or the explicitly attached file. No arbitrary computer-wide access.", {"path": "string"}),
    ("instagram_queue", "Read the configured Instagram content queue as data. Includes holds; publication records are not independent account evidence.", {}),
    ("instagram_prepare", "Check the next READY post and return ordered media paths and caption for manual upload. No publishing or script execution.", {}),
    ("store_products", "List saved product IDs, local files and checkout links. Local records are not live purchase verification.", {}),
    ("store_audit", "Check the selected local product file, SHA-256 and total PDF page count against its recorded expectation. Does not verify checkout delivery.", {"product_id": "string"}),
    ("store_export_listing", "Export the checked product's listing HTML and text to a new draft folder. Does not modify the website or publish.", {"product_id": "string"}),
    ("store_save_draft", "Save new listing, website or instagram draft text for a registered product. Drafts are local and unpublished.", {"product_id": "string", "channel": "string", "content": "string"}),
    ("gumroad_products", "Read the first page of products from the connected Gumroad account and save matching local catalog records. Never changes Gumroad.", {}),
    ("memory_list", "List saved facts and whether the user has reviewed them.", {}),
    ("memory_save", "Propose a memory fact. Model proposals require user review on the Memory page before future context uses them.", {"key": "string", "value": "string"}),
    ("memory_forget", "Remove a saved memory fact identified by its exact key, when the user requests it.", {"key": "string"}),
]


def schemas(names=None) -> list:
    return [{"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": {k: {"type": v} for k, v in args.items()},
                           "required": list(args), "additionalProperties": False}}}
            for name, desc, args in TOOLS if names is None or name in names]


def direct_command(text: str):
    """Only full, unambiguous matches bypass the model. Never discard trailing tasks."""
    text = re.sub(r"^(?:please|can you(?: please)?|could you(?: please)?|would you(?: please)?)\s+(?=(?:open|launch|run|start|read|check|list|show|help)\b)",
                  "", text.strip(), flags=re.I)
    if re.match(r"^(?:open|launch|run|start|read|check|list|show|help)\b", text, re.I):
        text = re.sub(r"(?:,\s*|\s+)please[.!?]*$", "", text, flags=re.I)
    address = text.strip()
    if re.fullmatch(r"https?://\S{1,1992}", address, re.I):
        return "read_web", {"url": address}
    domain = r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}(?::[0-9]{1,5})?(?:[/?#]\S*)?"
    def is_domain(value):
        # Windows executable names must retain desktop-app routing.
        return (len(value) <= 1992 and re.fullmatch(domain, value)
                and not re.search(r"\.(?:exe|cmd|bat|ps1|msi|lnk)$", value, re.I))
    if is_domain(address):
        return "read_web", {"url": "https://" + address}
    clean = text.strip().rstrip(".!?").strip()
    lower = clean.casefold()
    followup = re.fullmatch(
        r"(?:\[(?P<task_id>[a-f0-9]{8})\]\s+COMPLETE:\s+Found\s+\d{1,2}\s+web results for '[^\r\n]{1,500}'\.\s*)?"
        r"(?:where are (?:the |my )?results|show (?:me )?(?:the |my |last )?(?:search |web search )?results|what were the search results)",
        clean, re.I)
    if followup:
        return "show_search_results", {"task_id": (followup.group("task_id") or "").casefold()}
    if lower in {"help", "/help", "what can you do", "show tools"}:
        return "help", {}
    if lower in {"check my internet connection", "check internet", "check web", "can you access the web"}:
        return "check_web", {}
    if lower in {"check store website", "check my store website", "read my store website"}:
        return "store_website", {}
    if lower in {"read my website", "read my site", "show my website", "read website"}:
        return "store_website", {}
    if re.fullmatch(r"(?:check|audit|review) (?:my |the |store )?(?:website|site)(?: for (?:issues|problems|seo))?", lower):
        return "website_audit", {"url": ""}
    if re.fullmatch(r"(?:check|find) (?:my (?:website|site) for )?(?:broken links|website links|site links)", lower):
        return "website_links", {"url": ""}
    if lower in {"save website report", "export website report", "save site report"}:
        return "website_report", {}
    if lower in {"open my website", "open my site", "open store website", "open my store", "open my store website"}:
        return "open_store", {}
    match = re.fullmatch(r"(?:audit|check website|check site)\s+(https?://\S+)", clean, re.I)
    if match:
        return "website_audit", {"url": match.group(1)}
    match = re.fullmatch(r"(?:list|show) (?:my |workspace )?files", lower)
    if match:
        return "list_files", {"path": "."}
    match = re.fullmatch(r"(?:read file|/file)\s+(.+)", clean, re.I)
    if match:
        return "read_file", {"path": match.group(1).strip('"')}
    if lower in {"system health", "check system health", "show cpu", "check cpu"}:
        return "system_health", {}
    if lower in {"show my instagram queue", "list my instagram queue"}:
        return "instagram_queue", {}
    if lower in {"prepare next instagram post", "prepare next prompt copy studio post"}:
        return "instagram_prepare", {}
    if lower in {"show my products", "list my products", "store products", "show store products"}:
        return "store_products", {}
    if lower in {"sync gumroad", "load gumroad products", "list gumroad products"}:
        return "gumroad_products", {}
    if lower in {"show memory", "list memory", "what do you remember"}:
        return "memory_list", {}
    match = re.fullmatch(r"(?:audit product|/audit)\s+([A-Za-z0-9_-]{1,80})", clean, re.I)
    if match:
        return "store_audit", {"product_id": match.group(1)}
    match = re.fullmatch(r"(?:export listing|/export)\s+([A-Za-z0-9_-]{1,80})", clean, re.I)
    if match:
        return "store_export_listing", {"product_id": match.group(1)}
    match = re.fullmatch(r"(?:remember|/remember)\s+([^:]{1,100}):\s*(.+)", text.strip(), re.I | re.S)
    if match:
        return "memory_save", {"key": match.group(1).strip(), "value": match.group(2)}
    match = re.fullmatch(r"(?:forget memory|/forget)\s+([^\n]{1,100})", clean, re.I)
    if match:
        return "memory_forget", {"key": match.group(1).strip()}
    match = re.fullmatch(r"(?:search(?: the web)?(?: for)?|/search)\s+(.+)", clean, re.I)
    if match:
        return "search_web", {"query": match.group(1)}
    match = re.fullmatch(r"(?:read(?: web)?|/web)\s+(\S+)", clean, re.I)
    if match:
        value = match.group(1)
        if re.fullmatch(r"https?://\S+", value, re.I):
            return "read_web", {"url": value}
        if is_domain(value):
            return "read_web", {"url": "https://" + value}
    match = re.fullmatch(r"(?:open|launch|run|start)\s+(.+)", clean, re.I)
    if match:
        value = match.group(1).strip().strip('"')
        if re.fullmatch(r"https?://\S+", value, re.I):
            return "open_url", {"url": value}
        if is_domain(value):
            return "open_url", {"url": "https://" + value}
        # Multiple actions belong in the agent loop; do not launch only the first.
        if not re.search(r"\b(and|then|after|before)\b|[;\n]", value, re.I):
            return "open_app", {"app": value}
    return None


def public_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Use an HTTP(S) URL without embedded credentials.")
    if len(value) > 2000:
        raise ValueError("URL is too long.")
    if any(ord(c) < 32 for c in value):
        raise ValueError("URL contains control characters.")
    _ = parsed.port
    host = parsed.hostname.rstrip(".").casefold()
    if host in {"localhost", "localhost.localdomain"} or host.endswith((".localhost", ".local")):
        raise ValueError("Website tools use public addresses. Local services use their dedicated adapters.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError("Website tools cannot read private or loopback addresses.")
    return value


def format_search_results(result: dict) -> str:
    """Render actual retrieved evidence as plain text, without model synthesis."""
    results = result.get("results")
    if not isinstance(results, list):
        return ""
    lines = [str(result.get("summary", "Web search results"))]
    for index, item in enumerate(results[:6], 1):
        if not isinstance(item, dict):
            continue
        lines.extend(["", f"{index}. {str(item.get('title', 'Untitled result'))[:500]}",
                      str(item.get("url", ""))[:2000], str(item.get("snippet", ""))[:800]])
    return "\n".join(lines).strip()


def format_tool_result(result: dict) -> str:
    """Show retrieved content and useful fields, not just a success label."""
    search = format_search_results(result)
    if search:
        return search
    lines = [str(result.get("summary", "Tool result"))]
    for key in ("url", "path", "folder", "report_text"):
        if result.get(key):
            lines.append(str(result[key]))
    if result.get("text"):
        lines.extend(["", str(result["text"])])
    if result.get("output"):
        lines.extend(["", str(result["output"])])
    for key in ("products", "entries", "facts", "posts", "files", "audit"):
        if result.get(key):
            lines.extend(["", json.dumps(result[key], indent=2, ensure_ascii=False)])
    if result.get("truncated"):
        lines.append("[Only a bounded preview was retrieved.]")
    return "\n".join(lines).strip()


def _fetch_once(url, limit, timeout, cookie=""):
    def validate_target(value):
        public_url(value)
        p = urllib.parse.urlsplit(value)
        try:
            addresses = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80), type=socket.SOCK_STREAM)
        except socket.gaierror:
            if urllib.request.getproxies().get(p.scheme):
                # Some managed networks resolve public names at the HTTP proxy.
                # Literal local addresses were already rejected by public_url.
                return
            raise
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError("Website address resolves to a private network. No request was sent.")
    validate_target(url)
    request = urllib.request.Request(public_url(url), headers={"User-Agent": "StridentAI/3.1 (desktop task assistant)"})
    if cookie:
        request.add_header("Cookie", cookie)
    # Never forward the computed host cookie to another origin.
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            old, new = urllib.parse.urlsplit(req.full_url), urllib.parse.urlsplit(newurl)
            if cookie and (old.scheme, old.hostname, old.port) != (new.scheme, new.hostname, new.port):
                raise ValueError("The configured website redirected its browser cookie to a different origin.")
            validate_target(newurl)
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    opener = urllib.request.build_opener(Redirect())
    with opener.open(request, timeout=timeout) as response:
        body = response.read(limit + 1)
        content_type = response.headers.get("Content-Type", "")
        charset = response.headers.get_content_charset() or "utf-8"
        return body[:limit].decode(charset, errors="replace"), response.geturl(), content_type, len(body) > limit


def host_cookie_gate(text):
    return bool("slowAES.decrypt(c,2,a,b)" in text.replace(" ", "") and "__test=" in text and "aes.js" in text)


def fetch(url: str, limit=1_000_000, timeout=10, *, browser_cookie=False):
    started = time.monotonic()
    result = _fetch_once(url, limit, timeout)
    text, final, kind, truncated = result
    if not host_cookie_gate(text):
        return result
    if not browser_cookie:
        raise RuntimeError("This host requires a browser cookie. Set it as your Website URL in Settings or open it in the browser.")
    requested = urllib.parse.urlsplit(url)
    origin = urllib.parse.urlsplit(final)
    if (requested.scheme, requested.hostname, requested.port) != (origin.scheme, origin.hostname, origin.port):
        raise RuntimeError("Website cookie check redirected to another origin. Open the page in your browser.")
    values = {key: re.search(r'\b' + key + r'\s*=\s*toNumbers\(["\x27]([a-fA-F0-9]{32})["\x27]\)', text) for key in ("a", "b", "c")}
    if not all(values.values()):
        raise RuntimeError("Website returned an unfamiliar cookie check. No script was executed. Open it in the browser.")
    import pyaes
    key, iv, ciphertext = [bytes.fromhex(values[name].group(1)) for name in ("a", "b", "c")]
    cookie = "__test=" + pyaes.AESModeOfOperationCBC(key, iv=iv).decrypt(ciphertext).hex()
    remaining = timeout - (time.monotonic() - started)
    if remaining <= 0:
        raise TimeoutError("Website cookie check reached the request deadline.")
    # Only a fixed AES-CBC operation and one GET retry on the original URL.
    # No JS evaluation, credentials, browser profile or persistent cookie store.
    result = _fetch_once(url, limit, remaining, cookie)
    if host_cookie_gate(result[0]):
        raise RuntimeError("Website cookie check did not accept the request. Open it in the browser.")
    return result


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1
        if tag in {"p", "br", "li", "h1", "h2", "h3", "div"}:
            self.parts.append("\n")
    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.hidden = max(0, self.hidden - 1)
    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


class ToolRunner:
    def __init__(self, config: dict, attachment=""):
        self.config = config
        self.attachment = Path(attachment).resolve() if attachment else None
        self.explicit_memory = False

    def run(self, name: str, arguments: dict) -> dict:
        specs = {n: a for n, _, a in TOOLS}
        if name == "help":
            return {"ok": True, "summary": "Ready for tasks. Try: Check my website; Check my website for broken links; Read my website; Open my website; Save website report; List files; Show my products; Audit product <id>; Export listing <id>; Sync Gumroad; Show memory; Open Notepad; Search the web for <topic>. These commands work without model inference. Writing and complex requests use your selected local model. Coding page: write Python projects and test/debug them in Docker. Console: sandbox status; /code project-name describe the task; /testcode project-name. Coding requires a working Linux Docker engine and python:3.12-slim image. Live hosting edits require a hosting connection, which this app does not yet have.", "tools": [n for n, _, _ in TOOLS]}
        if name not in specs or not isinstance(arguments, dict):
            raise ValueError("Unknown tool or invalid arguments.")
        if set(arguments) != set(specs[name]) or any(not isinstance(v, str) for v in arguments.values()):
            raise ValueError(f"Invalid arguments for {name}.")
        return getattr(self, name)(**arguments)

    def open_app(self, app: str) -> dict:
        name = ALIASES.get(app.strip().casefold(), app.strip().casefold())
        if name in {"browser", "web browser", "default browser"}:
            return self.open_url("https://www.bing.com")
        custom = {ALIASES.get(k.casefold(), k.casefold()): v for k, v in self.config["apps"].items()}
        executable = custom.get(name)
        if not executable:
            if platform.system() != "Windows":
                raise RuntimeError("Built-in desktop app commands target Windows. Register a Windows executable in Settings.")
            built_in = WINDOWS_APPS.get(name)
            if not built_in:
                raise FileNotFoundError(f"'{app}' is not registered. Add its executable in Settings > Apps.")
            executable = shutil.which(built_in)
            if not executable:
                system = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / built_in
                executable = str(system) if system.is_file() else None
        if not executable or not Path(executable).is_file():
            raise FileNotFoundError(f"Executable was not found for {app}.")
        process = subprocess.Popen([executable], shell=False, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.25)
        code = process.poll()
        if code is not None and code != 0:
            raise RuntimeError(f"App launcher exited with code {code}.")
        # Store apps sometimes hand off and exit immediately. Do not invent window verification.
        return {"ok": True, "summary": f"Launch request accepted for {app}.",
                "executable": executable, "pid": process.pid, "launcher_exit_code": code,
                "verification": "launcher started; application window not independently verified"}

    def open_url(self, url: str) -> dict:
        url = public_url(url)
        if not webbrowser.open(url, new=2):
            raise RuntimeError("The default browser did not accept the open request.")
        return {"ok": True, "summary": "URL handed to the default browser.", "url": url,
                "verification": "browser handoff accepted; page rendering not verified"}

    def search_web(self, query: str) -> dict:
        if not query.strip() or len(query) > 500:
            raise ValueError("Search query must be 1 to 500 characters.")
        url = "https://www.bing.com/search?format=rss&q=" + urllib.parse.quote(query)
        text, final, _, _ = fetch(url)
        try:
            root = DefusedET.fromstring(text)
        except ET.ParseError as exc:
            raise RuntimeError("Search endpoint did not return results. Try Open https://www.bing.com in your browser.") from exc
        results = [{"title": item.findtext("title", ""), "url": item.findtext("link", ""),
                    "snippet": html.unescape(item.findtext("description", ""))[:800]}
                   for item in root.findall("./channel/item")[:6]]
        if not results:
            raise RuntimeError("No search results were returned; this may be a network or provider restriction.")
        return {"ok": True, "summary": f"Found {len(results)} web results for '{query}'.",
                "query": query, "source": final, "results": results}

    def show_search_results(self, task_id: str) -> dict:
        if task_id and not re.fullmatch(r"[a-f0-9]{8}", task_id):
            raise ValueError("Use the exact eight-character search task ID, or leave it empty for the latest search.")
        from .storage import State
        saved = State(self.config["data_dir"]).search_result(task_id)
        if not saved:
            return {"ok": False, "summary": "No saved web search results were found. Run Search the web for <topic> first."}
        saved_id, result = saved
        return {**{k: v for k, v in result.items() if k != "tool"}, "saved_task_id": saved_id, "from_saved": True,
                "summary": f"Saved search [{saved_id}] for '{result.get('query', '')}'. No new search was run."}

    def read_web(self, url: str) -> dict:
        configured = urllib.parse.urlsplit(self.config["store_url"])
        requested = urllib.parse.urlsplit(url)
        text, final, content_type, truncated = fetch(url, browser_cookie=(configured.scheme, configured.hostname, configured.port) == (requested.scheme, requested.hostname, requested.port))
        if "html" in content_type:
            parser = PageText()
            parser.feed(text)
            text = "".join(parser.parts)
        elif not any(t in content_type for t in ("text/", "json", "xml")):
            raise ValueError(f"Unsupported page format: {content_type}. Use a public text or HTML page.")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
        return {"ok": True, "summary": "Retrieved page text.", "url": final,
                "text": text[:16000], "truncated": truncated or len(text) > 16000}

    def check_web(self) -> dict:
        _, final, _, _ = fetch("https://www.microsoft.com", limit=4096, timeout=8)
        return {"ok": True, "summary": "Outbound HTTPS is working.", "url": final}

    def system_health(self) -> dict:
        import psutil
        memory = psutil.virtual_memory()
        return {"ok": True, "summary": "Current system resource sample.",
                "system_cpu_percent": psutil.cpu_percent(interval=0.2), "memory_percent": memory.percent,
                "memory_available_gb": round(memory.available / 1024**3, 2)}

    def _file_path(self, path: str) -> Path:
        root = Path(self.config["workspace"]).resolve()
        target = Path(path).expanduser()
        target = (root / target).resolve() if not target.is_absolute() else target.resolve()
        allowed = target == root or target.is_relative_to(root)
        if self.attachment and target == self.attachment:
            allowed = True
        if not allowed:
            raise PermissionError("Choose a file in the workspace or attach that file explicitly.")
        return target

    def list_files(self, path: str) -> dict:
        target = self._file_path(path or ".")
        entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold()))
        return {"ok": True, "summary": f"Listed {min(len(entries), 100)} entries.", "path": str(target),
                "entries": [{"name": p.name, "folder": p.is_dir()} for p in entries[:100]],
                "truncated": len(entries) > 100}

    def read_file(self, path: str) -> dict:
        target = self._file_path(path)
        with target.open("rb") as stream:
            data = stream.read(64001)
        if b"\0" in data:
            raise ValueError("Binary files are not supported in this release. Attach a text export.")
        return {"ok": True, "summary": "Read text file.", "path": str(target),
                "text": data[:64000].decode("utf-8-sig", errors="replace"), "truncated": len(data) > 64000}

    def instagram_queue(self):
        from .store import Store
        return Store(self.config).instagram_queue()

    def instagram_prepare(self):
        from .store import Store
        return Store(self.config).instagram_prepare()

    def store_products(self):
        from .store import Store
        return Store(self.config).products()

    def store_audit(self, product_id):
        from .store import Store
        return Store(self.config).audit(product_id)

    def store_export_listing(self, product_id):
        from .store import Store
        return Store(self.config).export_listing(product_id)

    def store_save_draft(self, product_id, channel, content):
        from .store import Store
        return Store(self.config).save_draft(product_id, channel, content)

    def gumroad_products(self):
        from .gumroad import Gumroad
        from .store import Store
        import hashlib
        result = Gumroad().products()
        store = Store(self.config)
        known = {p["remote_id"]: p for p in store.state.products() if p["remote_id"]}
        for p in result["products"]:
            record = known.get(p["id"], {"id": "gumroad-" + hashlib.sha256(p["id"].encode()).hexdigest()[:16], "expected_pages": None})
            record.update(title=p["name"], remote_id=p["id"])
            if p.get("short_url"):
                record["checkout_url"] = p["short_url"]
            store.save_product(record)
        return result

    def memory_list(self):
        from .storage import State
        facts = State(self.config["data_dir"]).facts()
        return {"ok": True, "summary": f"{len(facts)} saved memory facts.", "facts": facts}

    def memory_save(self, key, value):
        from .storage import State
        State(self.config["data_dir"]).fact(key, value, confirmed=self.explicit_memory,
            source="explicit user command" if self.explicit_memory else "agent proposal")
        return {"ok": True, "summary": "Saved memory." if self.explicit_memory else "Memory proposed; confirm it on the Memory page before it is used.",
                "key": key, "status": "confirmed" if self.explicit_memory else "review"}

    def memory_forget(self, key):
        if not self.explicit_memory:
            raise PermissionError("Use Forget memory <key> or the Memory page to remove a saved fact.")
        from .storage import State
        removed = State(self.config["data_dir"]).forget(key)
        return {"ok": removed, "summary": "Memory fact removed." if removed else "No saved fact has that exact key.", "key": key}

    def store_website(self):
        return self.read_web(self.config["store_url"])

    def open_store(self):
        return self.open_url(self.config["store_url"])

    def website_audit(self, url):
        from .website import audit
        return audit(url or self.config["store_url"], browser_cookie=not url or url == self.config["store_url"])

    def website_links(self, url):
        from .website import check_links
        return check_links(url or self.config["store_url"], browser_cookie=not url or url == self.config["store_url"])

    def website_report(self):
        from .website import save_report
        return save_report(self.config)
