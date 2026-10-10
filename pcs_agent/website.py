"""Public website checks with bounded requests and reviewable local reports."""
from __future__ import annotations
import json
import re
import time
import urllib.error
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urldefrag
import uuid
from .storage import State, utc
from .tools import fetch, public_url, PageText


class PageInfo(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = []
        self.in_title = False
        self.description = ""
        self.viewport = ""
        self.canonical = ""
        self.h1 = 0
        self.images = 0
        self.missing_alt = 0
        self.scripts = 0
        self.links = []
        self.base = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "h1":
            self.h1 += 1
        if tag == "script":
            self.scripts += 1
        if tag == "meta":
            name = a.get("name", "").casefold()
            if name == "description":
                self.description = a.get("content", "")
            if name == "viewport":
                self.viewport = a.get("content", "")
        if tag == "base" and not self.base:
            self.base = a.get("href", "")
        if tag == "link" and "canonical" in a.get("rel", "").casefold().split():
            self.canonical = a.get("href", "")
        if tag == "img":
            self.images += 1
            self.missing_alt += "alt" not in a
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)


def audit(url, *, browser_cookie=False):
    started = time.monotonic()
    public_url(url)
    try:
        html, final, content_type, truncated = fetch(url, timeout=8, browser_cookie=browser_cookie)
    except urllib.error.HTTPError as exc:
        return {"ok": False, "summary": f"Website returned HTTP {exc.code}. Open the site in your browser to check hosting access.",
                "url": url, "http_status": exc.code, "checked_utc": utc()}
    except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as exc:
        return {"ok": False, "summary": "Website request failed: " + str(exc), "url": url, "checked_utc": utc()}
    if "html" not in content_type.casefold():
        return {"ok": False, "summary": "Website audit requires an HTML page.", "url": final, "checked_utc": utc()}
    p = PageInfo()
    p.feed(html)
    body = PageText()
    body.feed(html)
    text = re.sub(r"\s+", " ", "".join(body.parts)).strip()
    title = "".join(p.title).strip()
    if re.search(r"just a moment|checking your browser|verify you are human|enable javascript and cookies", text[:2000], re.I):
        return {"ok": False, "summary": "The site returned an access challenge. Its public content was not verified. Open it in your browser.", "url": final, "checked_utc": utc()}
    issues = []
    for condition, message in ((not title, "Page title is missing."),
             (not p.description.strip(), "Meta description is missing."),
             (p.h1 == 0, "No main heading (H1) was found."),
             (p.h1 > 1, "Multiple H1 headings were found; review the page structure."),
             ("width=device-width" not in p.viewport.replace(" ", "").lower(), "Mobile viewport width is missing."),
             (p.missing_alt > 0, f"{p.missing_alt} images have no alt attribute."),
             (len(text) < 80 and p.scripts > 0, "The page may need JavaScript. Rendered content needs a browser check."),
             (truncated, "The source exceeded the 1 MB limit; this is a partial audit.")):
        if condition:
            issues.append(message)
    base = urljoin(final, p.base) if p.base else final
    links = list(dict.fromkeys(urldefrag(urljoin(base, link))[0] for link in p.links
                             if link.strip() and not link.startswith(("#", "mailto:", "tel:", "javascript:", "data:"))))
    links = [link for link in links if urlsplit(link).scheme in {"http", "https"}][:100]
    report = ["Website check", "URL: " + final, "Title: " + (title or "Missing"),
              "Description: " + (p.description.strip() or "Missing"),
              f"H1 headings: {p.h1}; images: {p.images}; page links: {len(links)}",
              "Findings:", *(issues or ["No issues found in these source checks."]),
              "Scope: one public HTML page. JavaScript, checkout delivery and hosting changes were not checked."]
    return {"ok": True, "summary": f"Website source checked: {len(issues)} finding(s).", "url": final,
            "checked_utc": utc(), "elapsed_seconds": round(time.monotonic() - started, 3),
            "title": title, "description": p.description.strip(), "issues": issues, "links": links,
            "text": text[:4000], "truncated": truncated, "report_text": "\n".join(report)}


def check_links(url, *, browser_cookie=False):
    result = audit(url, browser_cookie=browser_cookie)
    if not result["ok"]:
        return result
    start = time.monotonic()
    origin = urlsplit(result["url"])
    checked, skipped = [], []
    for link in result["links"]:
        target = urlsplit(link)
        # Same-origin page reads only. Query/action links and external checkout
        # links stay available in the report but are never clicked automatically.
        reason = ""
        if (target.scheme, target.hostname, target.port) != (origin.scheme, origin.hostname, origin.port):
            reason = "external link"
        elif target.query or re.search(r"(?:logout|signout|delete|remove|checkout|cart)", target.path, re.I):
            reason = "query or action link"
        elif len(checked) >= 8 or time.monotonic() - start >= 20:
            reason = "bounded check limit"
        if reason:
            skipped.append({"url": link, "reason": reason})
            continue
        try:
            _, final, _, truncated = fetch(link, limit=8192, timeout=min(3, max(.1, 20 - (time.monotonic() - start))), browser_cookie=browser_cookie)
            checked.append({"url": link, "reachable": True, "final_url": final})
        except urllib.error.HTTPError as exc:
            checked.append({"url": link, "reachable": False, "http_status": exc.code,
                            "classification": "broken" if exc.code in {404, 410} else "access or server error"})
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, RuntimeError) as exc:
            checked.append({"url": link, "reachable": False, "error": str(exc), "classification": "request failed"})
    failed = sum(not item["reachable"] for item in checked)
    lines = [f"Checked {len(checked)} same-origin page links; {failed} failed; {len(skipped)} skipped."]
    lines += [f"{'REACHABLE' if item['reachable'] else item.get('classification', 'FAILED').upper()}: {item['url']}" for item in checked]
    lines += ["Skipped: " + item["url"] + " (" + item["reason"] + ")" for item in skipped]
    return {"ok": True, "summary": lines[0], "url": result["url"], "checked_utc": utc(),
            "checked_links": checked, "skipped_links": skipped, "report_text": "\n".join(lines),
            "scope": "Up to eight same-origin page GET requests. No account or checkout actions."}


def save_report(config):
    saved = State(config["data_dir"]).tool_result({"website_audit", "website_links"})
    if saved is None:
        return {"ok": False, "summary": "Run Check my website or Check my website for broken links first."}
    task_id, evidence = saved
    root = Path(config["workspace"]).resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = root / "website_reports"
    target.mkdir(exist_ok=True)
    if not target.resolve().is_relative_to(root):
        raise PermissionError("Website report folder resolves outside the workspace.")
    folder = target / uuid.uuid4().hex[:12]
    folder.mkdir()
    payload = {"source_task_id": task_id, "saved_utc": utc(), "evidence": evidence}
    (folder / "report.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (folder / "report.txt").write_text(evidence.get("report_text", evidence["summary"]) + "\nChecked: " + evidence.get("checked_utc", "unknown") + "\n", encoding="utf-8")
    return {"ok": True, "summary": "Saved the latest website report. No new network check was made.",
            "folder": str(folder), "files": [str(folder / "report.txt"), str(folder / "report.json")], "published": False}
