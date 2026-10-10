"""Small native client for the documented product API. No SDK or legacy plugin."""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("Gumroad returned a redirect; the authenticated request was not forwarded.")


class Gumroad:
    def __init__(self, timeout=10):
        self.timeout = timeout

    def request(self, path, *, description=None):
        token = os.environ.get("PCS_GUMROAD_TOKEN", "").strip()
        if not token:
            raise RuntimeError("Connect Gumroad on the Store page using your API access token. It stays in this session and is never sent to the model.")
        if len(token) > 4096 or "\n" in token or "\r" in token:
            raise ValueError("Invalid Gumroad token format.")
        data = None if description is None else urllib.parse.urlencode({"description": description}).encode()
        request = urllib.request.Request("https://api.gumroad.com/v2" + path, data=data,
            method="GET" if data is None else "PUT", headers={"Authorization": "Bearer " + token,
            "User-Agent": "StridentAI/3.1", "Content-Type": "application/x-www-form-urlencoded"})
        try:
            opener = urllib.request.build_opener(NoRedirect())
            with opener.open(request, timeout=self.timeout) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise RuntimeError("Gumroad returned more data than the request limit.")
            result = json.loads(raw)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Gumroad HTTP {exc.code}. Check the token, its product permissions and account access.") from None
        except (urllib.error.URLError, TimeoutError) as exc:
            if description is not None:
                raise RuntimeError("Listing update result is uncertain. Check Gumroad before retrying; the request was not retried automatically.") from None
            raise RuntimeError("Gumroad did not respond within the configured timeout.") from None
        except ValueError:
            raise RuntimeError("Gumroad returned an invalid JSON response. Check the account before retrying a write.") from None
        if not isinstance(result, dict) or result.get("success") is not True:
            raise RuntimeError("Gumroad did not confirm success. Check the account and permissions; no automatic retry was made.")
        return result

    def products(self):
        result = self.request("/products")
        products = result.get("products")
        if not isinstance(products, list):
            raise RuntimeError("Gumroad did not return a products list.")
        # First-page scope is explicit. Do not guess new pagination tokens or fetch forever.
        clean = []
        for p in products[:100]:
            if not isinstance(p, dict) or not isinstance(p.get("id"), str) or not isinstance(p.get("name"), str):
                raise RuntimeError("Unexpected Gumroad product schema.")
            clean.append({k: p.get(k) for k in ("id", "name", "short_url", "price", "currency", "sales_count", "published")})
        return {"ok": True, "summary": f"Retrieved {len(clean)} products from Gumroad (first page).",
                "products": clean, "has_more": bool(result.get("next_page_url") or result.get("next_page_key")),
                "source": "https://api.gumroad.com/v2/products"}

    def product(self, product_id):
        if not re.fullmatch(r"[A-Za-z0-9_=-]{1,160}", product_id):
            raise ValueError("Invalid Gumroad product ID.")
        result = self.request("/products/" + urllib.parse.quote(product_id, safe=""))
        p = result.get("product")
        if not isinstance(p, dict) or p.get("id") != product_id:
            raise RuntimeError("Gumroad did not return the requested product.")
        return p

    def update_description(self, product_id, content, expected_name):
        if not isinstance(content, str) or not 1 <= len(content.strip()) <= 12000:
            raise ValueError("A listing description must contain 1 to 12,000 characters.")
        before = self.product(product_id)
        if before.get("name") != expected_name:
            raise RuntimeError("The remote product name changed. Sync and review the target before updating it.")
        result = self.request("/products/" + urllib.parse.quote(product_id, safe=""), description=content)
        p = result.get("product")
        if not isinstance(p, dict) or p.get("id") != product_id:
            raise RuntimeError("The update response did not identify this product. Check Gumroad before retrying.")
        return {"ok": True, "summary": "Gumroad accepted the description update.", "product_id": product_id,
                "fields_changed": ["description"], "verification": "API success response; customer checkout not tested"}
