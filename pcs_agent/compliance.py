"""Bounded evidence collection for explicit website compliance requests."""
from __future__ import annotations

import json
from pathlib import Path
import re
import time
import uuid

from .storage import utc
from .tools import public_url, format_tool_result


def request_url(command, configured_url):
    """Recognize an inspection request, never a quoted example or explanation.

    This route collects evidence only. It retains every requested action and
    does not interpret a checklist as permission to publish or change accounts.
    """
    text = command.strip()
    explicit = re.fullmatch(r'(?:/?compliance|check compliance|run compliance check)(?:\s+(https?://\S+))?[.!?]?', text, re.I)
    if explicit:
        return public_url((explicit.group(1) or configured_url).rstrip('.!?;'))
    if re.match(r'^(?:explain|summarize|translate|write|draft|what|how|why|remember|/remember)\b', text, re.I):
        return None
    if re.search(r"\b(?:do not|don't|don’t|never)\s+(?:check|audit|inspect|review)\b", text, re.I):
        return None
    action = re.search(r'\b(?:check|audit|inspect|review|optimi[sz]e)\s+(?:my\s+|the\s+)?(?:website|site)\b', text[:700], re.I)
    if not action or text.startswith(('"', "'")):
        return None
    if any(span.start() <= action.start() < span.end() for span in re.finditer(r'"[^"]*"|\x27[^\x27]*\x27', text)):
        return None
    markers = re.findall(r'\b(?:compliance|rls|hsts|csp|wcag|privacy|canonical|noindex|webhooks|indemnification|consent|seo|se0|security|metadata|keywords|hooks|app stores?)\b', text, re.I)
    if not markers:
        return None
    # Keep the existing short direct audit commands unchanged. Extended
    # inspection requests need evidence first even with just one scope marker.
    if re.fullmatch(r'(?:please\s+)?(?:check|audit|review) (?:my |the |store )?(?:website|site)(?: for (?:issues|problems|seo))?[.!?]?', text, re.I):
        return None
    # Prefer the address immediately after the website action. Never pick an
    # unrelated URL from the checklist or a returned page.
    tail = text[action.end():].lstrip(' \t(:')
    match = re.match(r'https?://[^\s),]+', tail, re.I) or re.match(r'(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}(?::[0-9]{1,5})?(?:/[^\s),]*)?', tail, re.I)
    url = match.group(0).rstrip('.!?;') if match else configured_url
    if match and not url.lower().startswith(('https://', 'http://')):
        url = 'https://' + url
    return public_url(url)


def requirement_rows(command):
    rows = []
    for line in command.splitlines():
        item = line.strip().lstrip('.-* ').strip()
        if not item:
            continue
        kind, evidence = 'scope', 'Keep the original request; additional work needs implementation and verification.'
        for pattern, category, needed in (
            (r'privacy labels|google or apple|signup|delete account', 'store and identity', 'Actual account flow, native build, SDK/data inventory and store declarations.'),
            (r'liabilit|governing|indemnif|terms|privacy policy|cookie policy|deletion policy', 'policies', 'Actual seller/data practices and reviewed policy text; public HTML cannot establish enforceability.'),
            (r'consent|gpc|capi|enhanced conversion|unsubscribe|phone|utm', 'data and marketing', 'Actual forms, tags, providers and server-side processing; add controls only for features used.'),
            (r'wcag|accessibility|button labels|inp', 'accessibility and performance', 'Keyboard/screen-reader/device checks and real-user performance measurements.'),
            (r'canonical|noindex|schema|lastmod|bylines|orphan|search bots|llms|keywords|meta data|page title', 'public discovery', 'Public pages, discovery files and deployed response evidence; one-page source checks are partial.'),
            (r'product requirement|technical requirement|app flow|design brief|background schema|implementation plan', 'planning', 'Application source and current behavior to document requirements, schema and release gates.'),
            (r'rls|row.level|keys|admin|rate limit|turnstile|csp|hsts|audit|https|tracking|backup|spf|dkim|dmarc|server|email|password|auth|\.env|secrets|sql|inputs|webhook|cors|debug|dependencies', 'source and deployment', 'Source, hosting/database/auth/DNS access and negative tests; these settings cannot be certified from a homepage.'),
        ):
            if re.search(pattern, item, re.I):
                kind, evidence = category, needed
                break
        rows.append({'requested': item, 'category': kind, 'status': 'unverified', 'needed': evidence})
    return rows


def save_report(config, payload, report_text):
    root = Path(config['workspace']).resolve()
    root.mkdir(parents=True, exist_ok=True)
    parent = root / 'website_reports'
    parent.mkdir(exist_ok=True)
    if not parent.resolve().is_relative_to(root):
        raise PermissionError('Website report folder resolves outside the workspace.')
    folder = parent / ('compliance-' + uuid.uuid4().hex[:12])
    folder.mkdir()
    (folder / 'report.json').write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    (folder / 'report.txt').write_text(report_text + '\n', encoding='utf-8')
    return [str(folder / 'report.txt'), str(folder / 'report.json')]


def collect(command, url, config, runner, emit, metrics):
    metrics['route'] = 'compliance checks'
    started = time.monotonic()
    budget = min(25, max(1, config['task_timeout'] - 5))
    evidence, deferred = [], []

    def record(name, operation):
        emit({'kind': 'log', 'stage': True, 'text': 'Compliance check: ' + name + '. No model inference.'})
        metrics['tool_calls'] += 1
        try:
            result = operation()
        except Exception as exc:
            result = {'ok': False, 'summary': str(exc)}
        evidence.append({'tool': name, **result})
        emit({'kind': 'tool', 'name': name, 'result': result})
        return result

    from .website import audit
    # A host challenge is a blocker, never a reason to compute a bypass cookie.
    page = record('website_audit', lambda: audit(url, browser_cookie=False))
    catalog = record('store_products', lambda: runner.run('store_products', {}))
    products = catalog.get('products', []) if catalog.get('ok') else []
    if not products:
        deferred.append('No registered product files were available. Add each real delivery file on the Store page; public product links alone do not verify purchased downloads.')
    byte_budget, attempts = 60_000_000, 0
    for product in products:
        product_id = product.get('id', '')
        reason = ''
        if attempts >= 10 or time.monotonic() - started >= budget:
            reason = 'bounded batch/time limit'
        else:
            try:
                path = Path(product.get('asset', ''))
                size = path.stat().st_size if path.is_file() else 0
                if size > 20_000_000 or size > byte_budget:
                    reason = 'bounded file-size limit'
            except OSError:
                size = 0
        if reason:
            deferred.append(f'Product {product_id}: deferred ({reason}). Run Audit product {product_id} separately.')
            continue
        attempts += 1
        byte_budget -= size
        record('store_audit', lambda pid=product_id: runner.run('store_audit', {'product_id': pid}))

    remaining = [
        'Website, product and application changes are not implemented by these checks. Strident has no hosting deployment adapter or app-store submission connection.',
        'Server security, database policies, account deletion, DNS/email, backups, policy enforceability, full WCAG conformance and Apple/Google approval remain unverified.',
        'Registered product checks cover local file existence, hash and PDF page count. They do not establish content accuracy, rights, accessibility or paid checkout delivery.',
    ]
    if page.get('ok') is not True:
        remaining.insert(0, 'Public website content was not verified: ' + page.get('summary', 'Request failed.'))
    rows = requirement_rows(command)
    payload = {'checked_utc': utc(), 'original_request': command, 'url': url,
               'evidence': evidence, 'requested_items': rows, 'deferred': deferred,
               'remaining': remaining, 'published': False, 'compliance_certified': False}
    report = '\n\n'.join([
        'Available checks finished. The full compliance request remains unfinished.',
        *(format_tool_result(item) for item in evidence),
        'Remaining work:\n' + '\n'.join('- ' + item for item in remaining + deferred),
        'Requested scope (unverified unless supported by the evidence above):\n' + '\n'.join('- ' + row['requested'] + ' [' + row['category'] + ']' for row in rows),
        'Original request:\n' + command,
    ])
    saved = record('compliance_report', lambda: {'ok': True, 'summary': 'Saved the full request, evidence and remaining work locally.', 'files': save_report(config, payload, report), 'published': False})
    reply = report + '\n\n' + format_tool_result(saved)
    return {'status': 'needs_attention', 'summary': f'Available compliance checks finished; {attempts}/{len(products)} local products attempted. Implementation and approval remain unfinished.',
            'reply': reply, 'evidence': evidence,
            'history': [{'role': 'user', 'content': command}, {'role': 'assistant', 'content': reply[:6000]}]}
