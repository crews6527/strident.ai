# Cleaned-source verification

Version: 3.1.2. Checked October 10, 2026 UTC (October 9 in America/Chicago).

- The complete retained application suite passed: 131 tests in 47.967 seconds on CPython 3.12.14 with Qt's offscreen platform on Linux.
- Checks cover spawned task workers, cancellation, deadlines, direct command routing, memory/storage, PDF product audits, listing exports, simulated Gumroad requests, website access/metadata, saved searches, CurbSentry adapter behavior and Qt interface flows.
- Two added end-to-end idle checks verify that pre-existing settings/database bytes remain unchanged and that an attempted startup model request is blocked, counted and causes diagnostic failure. These checks caught and corrected defaults loaded before the temporary data directory was selected.
- The six pinned dependency packages installed together and passed uv pip check. Python sources parse and local relative imports resolve.
- The final separate idle sample ran for 10.435 seconds, using 0.040358 console CPU seconds: 0.387% of one core and 0.043% of the nine-core test machine. It submitted zero tasks and attempted zero Ollama requests. This is a console-process sample in a shared Linux environment, not a Windows device benchmark. Microphone hardware was not instrumented.
- Archives, executables, virtual environments, caches, private app data, old release/benchmark output and the standalone CurbSentry/storefront applications are excluded from the final source tree. The optional read-only CurbSentry adapter remains.
- The active portrait is retained and its shortcut icon was regenerated from it. License texts are retained. Historical upstream comparison claims are not used as evidence for this cleaned build.
- SHA256SUMS.txt records every packaged file other than itself. The downloadable ZIP is checked for CRC integrity and every listed SHA-256 before delivery.

The test environment had no real Ollama inference service, authenticated Gumroad account, Windows desktop, Windows tray or CurbSentry production connection. Those device/account flows remain unverified. Existing unit and spawned-process fixtures establish the exercised application behavior, not a successful real customer checkout or a faster model runner.

Native Windows launch, shortcut creation, tray behavior and your installed model should be checked after restoring or installing. Install-Strident.cmd reruns the application suite with isolated temporary test data on the target computer.
