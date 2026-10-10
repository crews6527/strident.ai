"""Store records, product-file evidence and native Instagram content handoff."""
from __future__ import annotations
import hashlib
import html
import json
import re
from pathlib import Path
import uuid
from .storage import State, utc


def text_file(path, limit=128000):
    path = Path(path)
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit or b"\0" in raw:
        raise ValueError("Content file is binary or exceeds its size limit.")
    return raw.decode("utf-8-sig")


def web_address(value):
    from .tools import public_url
    return public_url(value)


class Store:
    def __init__(self, config):
        self.config = config
        self.state = State(config["data_dir"])

    def save_product(self, product):
        product_id = str(product.get("id", ""))
        title = str(product.get("title", "")).strip()
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", product_id) or not 1 <= len(title) <= 200:
            raise ValueError("Use a product ID with letters, numbers, underscores or hyphens and a title under 200 characters.")
        asset = str(product.get("asset", ""))
        if asset and (not Path(asset).is_absolute() or not Path(asset).is_file()):
            raise ValueError("Choose an existing product file using Browse.")
        checkout = str(product.get("checkout_url", "")).strip()
        if checkout:
            web_address(checkout)
        pages = product.get("expected_pages")
        if pages is not None and (type(pages) is not int or not 1 <= pages <= 10000):
            raise ValueError("Expected page count must be blank or 1 to 10,000.")
        description = str(product.get("description", ""))
        remote_id = str(product.get("remote_id", ""))
        if len(description) > 12000 or len(remote_id) > 160:
            raise ValueError("Product record exceeds its size limit.")
        self.state.upsert_product({"id": product_id, "title": title, "asset": asset,
            "checkout_url": checkout, "expected_pages": pages, "description": description, "remote_id": remote_id})
        return {"ok": True, "summary": "Saved the local product record.", "product_id": product_id}

    def products(self):
        rows = self.state.products()
        return {"ok": True, "summary": f"{len(rows)} local product records.", "products": rows}

    def audit(self, product_id):
        p = self.state.product(product_id)
        issues = []
        audit = {"checked_utc": utc(), "product_id": product_id, "title": p["title"],
                 "scope": "local file; checkout delivery unverified", "checkout_url": p["checkout_url"]}
        if not p["asset"]:
            issues.append("Choose the product file on the Store page.")
        else:
            asset = Path(p["asset"])
            if not asset.is_file() or not asset.stat().st_size:
                issues.append("Product file is missing or empty.")
            elif asset.stat().st_size > 100_000_000:
                issues.append("Product exceeds the 100 MB audit limit.")
            else:
                # Bound memory while hashing large product files.
                initial = asset.stat()
                digest = hashlib.sha256()
                with asset.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                audit.update(bytes=asset.stat().st_size, sha256=digest.hexdigest(), file=str(asset))
                if asset.suffix.casefold() == ".pdf":
                    from pypdf import PdfReader
                    with asset.open("rb") as stream:
                        pdf = PdfReader(stream, strict=False)
                        if pdf.is_encrypted:
                            issues.append("PDF is encrypted; its contents were not checked.")
                        else:
                            audit["pages"] = len(pdf.pages)
                            audit["expected_pages"] = p["expected_pages"]
                            if p["expected_pages"] is not None and p["expected_pages"] != audit["pages"]:
                                issues.append(f"Page count mismatch: expected {p['expected_pages']}, found {audit['pages']} total PDF pages.")
                            if not audit["pages"]:
                                issues.append("PDF contains no pages.")
                else:
                    audit["content_validation"] = "file existence and hash only"
                final = asset.stat()
                if (initial.st_size, initial.st_mtime_ns, initial.st_ino) != (final.st_size, final.st_mtime_ns, final.st_ino):
                    issues.append("Product file changed during the check; check it again before exporting.")
        if not p["checkout_url"]:
            issues.append("Add the real checkout link before exporting a store listing.")
        audit["issues"] = issues
        audit["local_pass"] = not issues
        self.state.save_audit(product_id, audit)
        return {"ok": not issues, "summary": "Local product checks passed; checkout delivery still needs verification." if not issues else "Product needs attention: " + " ".join(issues), "audit": audit}

    def save_draft(self, product_id, channel, content):
        draft_id = self.state.draft(product_id, channel, content)
        return {"ok": True, "summary": "Draft saved locally for review.", "draft_id": draft_id,
                "channel": channel, "published": False}

    def output(self, title):
        workspace = Path(self.config["workspace"]).resolve()
        if not workspace.is_dir():
            raise ValueError("Create or choose an existing workspace folder in Settings first.")
        target = workspace / "store_drafts"
        target.mkdir(exist_ok=True)
        if not target.resolve().is_relative_to(workspace):
            raise PermissionError("Draft folder resolves outside the workspace.")
        folder = target / (title + "-" + uuid.uuid4().hex[:12])
        folder.mkdir()
        return folder

    def export_listing(self, product_id):
        p = self.state.product(product_id)
        audit = self.audit(product_id)
        if not audit["ok"]:
            raise ValueError(audit["summary"])
        drafts = [d for d in self.state.drafts(product_id) if d["channel"] in {"listing", "website"}]
        description = drafts[0]["content"] if drafts else p["description"]
        if not description.strip():
            raise ValueError("Add or draft the listing description before exporting.")
        folder = self.output(product_id)
        esc = html.escape
        page = "<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>" + esc(p["title"]) + "</title><style>body{max-width:760px;margin:64px auto;padding:24px;font:18px/1.6 system-ui;color:#172631}a{display:inline-block;padding:12px 24px;background:#164b45;color:white;border-radius:6px;text-decoration:none}p{white-space:pre-wrap}</style><main><h1>" + esc(p["title"]) + "</h1><p>" + esc(description) + "</p><a rel=\"noopener\" href=\"" + esc(p["checkout_url"], quote=True) + "\">View product and checkout</a></main></html>"
        (folder / "listing.html").write_text(page, encoding="utf-8")
        (folder / "description.txt").write_text(description, encoding="utf-8")
        (folder / "local_check.json").write_text(json.dumps(audit["audit"], indent=2), encoding="utf-8")
        return {"ok": True, "summary": "Exported listing files for review and upload.", "folder": str(folder),
                "files": [str(folder / n) for n in ("listing.html", "description.txt", "local_check.json")],
                "published": False, "verification": "local file checked; checkout delivery unverified"}

    def queue(self):
        root = Path(self.config["instagram_folder"])
        if not self.config["instagram_folder"] or not root.is_dir():
            raise ValueError("Choose the existing Instagram content folder in Settings. It needs manifest.json and posts/; no Python scripts will be run.")
        raw = text_file(root / "manifest.json", 256000)
        manifest = json.loads(raw)
        if not isinstance(manifest, dict) or manifest.get("schema_version") != 1 or manifest.get("account") != "prompt_copy_studio":
            raise ValueError("Expected the Prompt Copy Studio content manifest (schema 1).")
        posts = manifest.get("posts")
        if not isinstance(posts, list) or len(posts) > 500:
            raise ValueError("Invalid post queue.")
        state_path = root / "state.json"
        state = json.loads(text_file(state_path, 256000)) if state_path.exists() else {"posts": {}}
        if not isinstance(state, dict) or not isinstance(state.get("posts"), dict):
            raise ValueError("Invalid content state data.")
        result, seen = [], set()
        for p in posts:
            if not isinstance(p, dict) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", str(p.get("id", ""))) or p["id"] in seen:
                raise ValueError("Invalid or duplicate post ID.")
            seen.add(p["id"])
            record = state["posts"].get(p["id"], {})
            if not isinstance(record, dict):
                raise ValueError("Invalid post state.")
            status = "recorded_published" if record.get("published_url") else "hold" if p.get("hold_reason") and not record.get("released_at") else "ready"
            result.append({"id": p["id"], "title": str(p.get("title", p["id"]))[:200], "status": status,
                "hold_reason": str(p.get("hold_reason") or "")[:1000], "published_url": str(record.get("published_url") or "")[:2000]})
        return root.resolve(), posts, result

    def instagram_queue(self):
        _, _, posts = self.queue()
        return {"ok": True, "summary": f"{len(posts)} content records for @prompt_copy_studio.", "posts": posts,
                "verification": "local queue only; account publication not independently checked"}

    def instagram_prepare(self):
        root, posts, labels = self.queue()
        first = next((label for label in labels if label["status"] == "ready"), None)
        if not first:
            raise ValueError("No ready post remains. Review the queue holds or recorded publications.")
        post = next(p for p in posts if p["id"] == first["id"])
        folder = (root / "posts" / post["id"]).resolve()
        if not folder.is_relative_to(root):
            raise PermissionError("Post folder is outside the content folder.")
        media = post.get("media")
        if not isinstance(media, list) or not 1 <= len(media) <= 20:
            raise ValueError("Post media list is invalid.")
        paths = []
        for name in [*media, post.get("cover"), "caption.txt"]:
            if not isinstance(name, str) or not name or Path(name).is_absolute():
                raise ValueError("Post assets must use relative filenames.")
            path = (folder / name).resolve()
            if not path.is_relative_to(folder) or not path.is_file() or not path.stat().st_size:
                raise ValueError("A post asset is missing, empty or outside the content folder.")
            paths.append(path)
        caption = text_file(paths[-1], 10000).strip()
        if not caption or len(caption) > 2200:
            raise ValueError("Caption is empty or longer than 2,200 characters.")
        return {"ok": True, "summary": "Prepared the next post's media order and caption for manual upload.",
                "post_id": post["id"], "account": "prompt_copy_studio", "folder": str(folder),
                "media": [str(p) for p in paths[:len(media)]], "caption": caption, "cover": str(paths[-2]),
                "published": False, "verification": "local assets checked; no account request was made"}
