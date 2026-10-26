# Repair and verification, October 22, 2026

Version: 3.3.1. Scope: the supplied Strident Python desktop project and private browser console.

## Confirmed defects and repairs

The uploaded runtime.py ended after 31 lines and referenced an undefined _execute. tools.py contained imports plus a truncation comment, with no tool implementations. SHA256SUMS.txt contained PLACEHOLDER. These defects blocked imports/startup and integrity checks. Complete runtime/tools implementations were recovered from crews6527/strident.ai commit f48190a and verified against the existing tests. The repository itself was not modified.

The directive attachment contained two consecutive JSON objects, unescaped multiline strings and an erroneous period after an array. It was normalized into docs/directives.json; the full owner checklist is preserved in docs/owner-directives.txt. Permanent policy code applies across writing, action, coding and member model paths. Explicit /role supports the eleven existing engineering roles. Security permissions are enforced independently of generated text. This does not retrain model weights or make source immutable to someone with filesystem access.

Added working administrator and user login/logout, first-admin setup, administrator-created users, password change, local password recovery, session revocation, rate limits, CSRF checks and member account/data deletion. Members have isolated task databases and writing-only runtimes. No untrusted member can invoke desktop tools through a prompt or API setting. Browser credentials are not kept in localStorage/sessionStorage.

Added Live-Test.cmd/live_test.py and Setup-Admin.cmd/manage_accounts.py. The test server uses .live-test data, loopback binding and the real worker engine; no fake model responses are substituted. The native personal console remains protected by the OS account. Added private-use privacy, terms, accessibility/AI notices and service-readiness documentation. Removed three redundant .cpgz launcher archives from the new package; their original uploaded copy remains in file version history.

The dependency audit found six vulnerabilities in pypdf 6.20.0. Updated to 6.21.1 and refreshed the license notice. The post-upgrade audit of all six pinned runtime packages found no known vulnerabilities. This checks advisory records, not the entire OS, Ollama, model, browser, optional Docker image or hosting stack.

## Verification evidence

- 195 automated tests passed in the dedicated Python 3.12 virtual environment (60.175 seconds). Covers existing desktop/tool behavior plus new authentication, session revocation, password reset, cross-user access denial, CSRF, role prompts and member prompt-injection tool rejection.
- Real headless Chromium browser flow passed: bootstrap administrator, administrator login/logout buttons, create user, user login/logout buttons, separate history, spawned Help command, password change/re-login, deletion, policy links and 390px viewport. No JavaScript errors.
- Idle diagnostic passed: five-second isolated Qt sample, zero submitted tasks and zero attempted Ollama requests, about 0.29% of one CPU core in this sample.
- Python dependency consistency check passed. Post-upgrade advisory audit passed. Package manifest rebuilt and integrity checked.
- Test fixtures exercised stalled model responses, partial-answer preservation, cancellation, progress-renewed inactivity deadlines and overall ceilings. These fixtures do not establish actual qwen3.5:2b throughput or successful generation on your PC.

Initial validation failures exposed an overly broad role match, old hardcoded version assertions and a global interpreter installation incompatible with isolated startup. The role match now requires explicit role syntax; tests check the actual version; final checks ran in the dedicated virtual environment. No failing check was suppressed.

## Remaining external checks and service gates

There is no installed Ollama model in this execution environment. Real model generation must be tested on your computer using Test saved model. Windows shortcuts/installers were inspected, while runtime verification here used Linux; Windows CI has not run for these changes. Phone/Tailscale, actual Docker execution and public hosting were not live-tested.

Public customer service remains gated on production hosting/TLS, verified signup and recovery, applicable Google/Apple setup, MFA, appropriate anti-abuse, capacity/tenant resource isolation, backup scheduling/restore, security assessment, accessibility testing, operator identity/contact and reviewed commercial terms. Payments, analytics and marketing integrations are not installed. The policy documents state actual private behavior; they cannot guarantee freedom from lawsuits or app-store approval.

PyQt licensing needs review before proprietary distribution. Its official licensing is GPLv3 or commercial; retaining third-party notices is not a substitute for choosing and complying with a licensing path.

Sources: https://en.riverbankcomputing.com/software/pyqt ; https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html ; https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
