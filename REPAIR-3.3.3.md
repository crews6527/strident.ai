# Strident.AI 3.3.3 repair

This update fixes thinking-control detection for Ollama metadata that lists the thinking capability without a thinking.values descriptor. Explicit level-based controls remain unchanged. Requests now log the effective thinking value, context size, output limit and streaming mode. No timeouts were increased, models substituted or permanent policy removed.

Settings validation now rejects file-size display labels such as qwen3.5:2b · 2.56 GB. Select the exact installed tag qwen3.5:2b. The supplied archive already used exact tags in its refreshed model selectors; this change guards manual or imported display labels too.

Dropped connections now produce an explanation that distinguishes a disconnect from a response timeout and points to the Ollama server output. This improves diagnosis; it does not prove the cause of the earlier disconnect.

## Install and test on Windows

1. Close Strident and its preview, leaving Ollama running.
2. Extract this ZIP into a new folder. Keep the previous installation as a backup.
3. Run Install-Strident.cmd from the extracted folder. It installs pinned dependencies, runs the checks and creates a shortcut pointing to that folder.
4. Run Launch-Strident.cmd from that same folder.
5. In Settings, refresh models, select qwen3.5:2b without a size label and save. Check both the main and optional writing model selections.
6. Run /testmodel. Confirm version 3.3.3 and the new source folder in the log. For a thinking-capable model with Boolean controls or capability-only metadata, the request-settings log should show thinking=False.
7. If the test fails, export the transcript and capture the corresponding ollama serve output.

The earlier PowerShell API test returned Hello in 2.5 seconds with thinking disabled. The earlier Strident transcript reported a disconnected request, not a confirmed 120-second timeout. This repair has not been live-tested against the user's Windows Ollama instance. Successful local automated checks do not establish successful model generation on that PC.

## Verification

Checks ran on CPython 3.12.14 with the complete pinned requirements. The full suite ran 214 tests; 213 passed and the launch integrity test identified the edited files' stale checksums. After regenerating SHA256SUMS.txt, all six launch-guard tests passed. All 17 Ollama tests passed in the full run. A five-second Qt idle sample passed with zero submitted tasks and zero Ollama requests. These are automated and simulated-server checks, not a Windows live-model certification.
