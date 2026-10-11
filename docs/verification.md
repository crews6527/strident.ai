# Cleaned-source verification

Version: 3.2.0. Checked October 11, 2026 (UTC and America/Chicago).

## Coding release checks

- The application suite passed 152 tests, including 17 new coding checks. These cover source/path limits, symlinks, immutable revisions, exact model selection, malformed/truncated replies, bounded repairs, saved failure evidence, retesting without inference, empty/skipped suites, fail-closed setup, Docker restriction arguments and cleanup failures. The supervisor also ran fixed trusted fixtures to verify passing/failing tests, a 12 KB output bound and deadline handling; these host fixture runs do not establish container isolation.
- Cancellation was exercised with a real spawned worker and its subprocess. The owned subprocess was stopped, the known container name was passed to cleanup, and observed evidence survived cancellation. Docker cleanup calls were simulated.
- A 10.005-second idle sample passed with zero submitted tasks, zero Ollama requests and 0.026490 console CPU seconds (0.265% of one core; 0.029% of nine logical cores). This measures the Linux Qt console process, not the user's Windows PC.
- Docker and real Ollama inference are unavailable here. Container startup, actual isolation, Windows Docker Desktop behavior and real model coding quality remain unverified. Check the engine/image and run a small coding project on the target computer before daily use. No generated code was executed on the host as a fallback.
- The archive excludes generated coding projects and their logs; these remain in the user's workspace and need their own backup.

## Previous direct-command release checks

- The complete application suite passed: 135 tests in 24.382 seconds on CPython 3.12.14 with Qt's offscreen platform on Linux. Four added routing/runtime tests exercise bare-domain open/read, executable and multi-action handling, browser handoff without app lookup or inference, and visible browser failure. Basic command checks also cover polite phrasing.
- Checks cover spawned task workers, cancellation, deadlines, direct command routing, memory/storage, PDF product audits, listing exports, simulated Gumroad requests, website access/metadata, saved searches, CurbSentry adapter behavior and Qt interface flows.
- Two added end-to-end idle checks verify that pre-existing settings/database bytes remain unchanged and that an attempted startup model request is blocked, counted and causes diagnostic failure. These checks caught and corrected defaults loaded before the temporary data directory was selected.
- The six pinned dependency packages installed together and passed uv pip check. Python sources parse and local relative imports resolve.
- The final separate idle sample ran for 10.003 seconds, using 0.012669 console CPU seconds: 0.127% of one core and 0.014% of the nine-core test machine. It submitted zero tasks and attempted zero Ollama requests. The diagnostic now uses a precise Qt timer because a coarse timer ended one sample early. The two idle diagnostic tests passed again after that change. This is a console-process sample in a shared Linux environment, not a Windows device benchmark. Microphone hardware was not instrumented.
- Archives, executables, virtual environments, caches, private app data, old release/benchmark output and the standalone CurbSentry/storefront applications are excluded from the final source tree. The optional read-only CurbSentry adapter remains.
- The active portrait is retained and its shortcut icon was regenerated from it. License texts are retained. Historical upstream comparison claims are not used as evidence for this cleaned build.
- SHA256SUMS.txt records every packaged file other than itself. The downloadable ZIP is checked for CRC integrity and every listed SHA-256 before delivery.

The test environment had no real Ollama inference service, authenticated Gumroad account, Windows desktop, Windows tray or CurbSentry production connection. Those device/account flows remain unverified. Existing unit and spawned-process fixtures establish the exercised application behavior, not a successful real customer checkout or a faster model runner.

Native Windows launch, shortcut creation, tray behavior and your installed model should be checked after restoring or installing. Install-Strident.cmd reruns the application suite with isolated temporary test data on the target computer.

## Basic website command repair

Before this repair, `open promptcopystudio.42web.io` selected `open_app`, which
asked the user to register the domain as an executable. It now selects `open_url`
with `https://promptcopystudio.42web.io` and bypasses Ollama. `read` followed by a
bare domain likewise selects page retrieval. Polite forms such as `Please open
Notepad` and `Could you please open promptcopystudio.42web.io?` retain direct
routing. Requests containing multiple actions keep the complete original task.

Browser handoff is mocked in the regression test; this does not demonstrate a
rendered page or working default-browser association on the user's Windows PC.
The tests establish the corrected dispatcher and failure reporting. The existing
Strident CurbSentry adapter was separately exercised against the repaired native
CurbSentry service on Linux with synthetic confirmed sightings; its alert and
acknowledgement responses were compatible.
