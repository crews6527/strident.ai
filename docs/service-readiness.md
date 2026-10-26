# Architecture and release gates

## Repaired architecture

Windows launchers use the package Python virtual environment. Qt and the loopback browser console share the administrator Controller. Each Controller supervises spawned worker processes with cancellation, an inactivity deadline renewed by actual progress, and a separate overall ceiling. Tool evidence survives failure. Runtime and tools were restored from repository commit f48190a; the uploaded replacements omitted their implementations.

The permanent policy is pcs_agent/policy.py, included in writing, tool-capable, coding, diagnostic and member inference paths. All eleven roles are available through /roles and /role. Ordinary commands such as Audit product retain their direct routing. The original owner checklist and repaired JSON are under docs. Source changes can change policy; this is not tamper-proof model training. Prompt injection cannot grant member tool privileges because their execution path has no ToolRunner.

Authentication uses sqlite accounts, scrypt N=32768/r=8/p=3, random salts, 15-character minimum passwords, opaque sessions hashed in the database, eight-hour expiry, HttpOnly/SameSite=Strict cookies, CSRF headers and same-origin checks. Password reset revokes all account sessions; logout revokes the current session. User creation is administrator-only. No default credentials are shipped. Initial desktop-key setup is disabled after an administrator exists. Roles come from the server database, never submitted client role fields.

Administrator tasks use existing studio.sqlite3 and task-traces.sqlite3. Member tasks use members/<random account ID>/ with independent databases, controllers and history. Every member endpoint selects the runtime from the authenticated account. Members cannot change host settings, read host files, use store integrations or execute tools. SQLite does not provide PostgreSQL-style RLS; separate databases and server authorization enforce this private test boundary. This is not infrastructure isolation suitable for arbitrary untrusted executable customer workloads.

## API and behavior

GET /api/me returns the current account and CSRF token. POST /api/login and /api/logout create/revoke sessions. POST /api/bootstrap creates the first administrator with the desktop setup key. POST /api/users creates members. POST /api/delete-account deletes the authenticated member and its local data. GET /api/tasks, /api/events and /api/export are scoped to the authenticated runtime. POST /api/tasks, /api/cancel and /api/retry operate in that runtime. Configuration/model endpoints require administrator access.

## Private testing

Run Install-Strident.cmd, then Live-Test.cmd. This starts the real application server with isolated .live-test data and workspace, preserving personal data. Create an administrator using the displayed setup key, log in, create a member, then exercise both logout/login buttons. Configure the exact installed Ollama model in Settings and press Test saved model. Direct Help works without Ollama. For normal personal operation use Setup-Admin.cmd and Live-Preview.cmd after installation. Member accounts are intended for a small private test group.

The server binds 127.0.0.1 only. Local HTTP is an explicit development exception. Use the existing private Tailscale HTTPS setup for phone access. Remote allowed hosts receive Secure cookies and HSTS; do not expose this stdlib development server directly to the public internet. No public deployment was performed.

## Requirements that remain deployment-dependent

Before public service: production HTTP stack/reverse proxy, TLS and host configuration; persistent distributed rate limiting and capacity limits; appropriate Turnstile/anti-abuse; verified signup, email/password recovery and Google/Apple provider configuration where required; MFA for administrators; documented session/device controls; per-tenant infrastructure limits; backup scheduling and restore drills; uptime/error alerting with redaction; security assessment; accessibility testing; operator-reviewed legal documents and contact details; license review and app-store submissions. Payments, billing webhooks, unsubscribe, consent banners and marketing DNS must be added only if those features are introduced.

No analytics or advertising is installed because no consent-backed deployment exists. Private account pages remain noindex. Marketing SEO, LocalBusiness JSON-LD, sitemap, llms.txt, marketing consent and real-user INP measurement belong to the public site, not this private console. No website DNS, hosting, database-provider, store or payment credentials were supplied.

## Operations and incident response

Stop the service before moving data. Back up the complete configured data directory and workspace to encrypted operator-controlled storage. Test restore in an isolated directory before replacing active data. Backups contain personal data and password hashes; never include them in releases. After compromise, stop access, preserve restricted evidence, reset affected passwords (revoking sessions), rotate integration secrets, investigate exposure and follow applicable notification requirements. Do not log secrets or publish transcripts unreviewed.

## References

https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
https://en.riverbankcomputing.com/software/pyqt

PyQt is GPLv3 or commercially licensed. A proprietary redistributed desktop product needs an appropriate licensing path; the current license notices do not by themselves grant a commercial PyQt license. Review Qt and other bundled dependencies separately.
