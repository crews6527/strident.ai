Historical documentation from the supplied build. For the October 22 repair and account behavior, read repair-report-2026-10-22.md and service-readiness.md.

# Strident.AI repair report

Prepared October 15, 2026. Delivered source version: 3.3.0. Base: the original `crews6527/strident.ai` repository at commit `992a0426706a3e0a83d2b2c78376ef6acee6ed38` (version 3.2.3), preserving its newer coding/compliance and existing business workflows.

## Findings

The source contains two independent stops. `pcs_agent/config.py` defaults `model_timeout` to 45 seconds and `task_timeout` to 60 seconds. `pcs_agent/provider.py` applies the 45-second socket wait to `/api/chat`. The old `Controller._loop` in `pcs_agent/runtime.py` unconditionally terminated a worker after `task_timeout`, even if the model was streaming or tools were making progress. This is a confirmed code defect for tasks needing longer than that configured deadline. No literal 59-second constant was found. Your actual saved runtime configuration was not supplied, so the exact 59-second value in the earlier log cannot be traced further here.

Your earlier error also establishes that one Ollama request did not provide a server response within 45 seconds. That failure occurs before the 60-second task cutoff. The code already requested streaming, so enabling streaming alone would not repair it. A cold model load, limited RAM/VRAM, CPU inference, a busy Ollama queue or a model/runtime problem can cause a slow first response, but none of those device causes has been established without your PC's model diagnostic. Increasing a timeout would not establish model health. The repair keeps the 45-second socket budget unchanged.

The verification suite uses simulated model servers for protocol/failure checks and isolated data for GUI tests. Passing that suite never established that your actual selected Ollama model could generate a reply on Windows. The restored Test-Ollama and Check-Strident helpers run genuine bounded generation on the installed model when executed on your PC. A successful version or model-list request is reported separately from successful inference.

The original action loop could also mark an ordinary model response complete without any action-tool evidence. This update reports needs_attention for an action request answered without tools, and refuses inferred action workflows when the selected model does not advertise tools. Text generation, launcher handoff, retrieved HTML and verified saved output remain different outcomes. No model can make unsupported adapters perform actions.

Some compound direct commands unnecessarily went through inference. `and then` and `and` now route directly only when all complete steps are recognized. An incomplete or mixed request remains intact for the model. Memory values and quoted data remain protected from splitting.

## What changed

- Worker supervision distinguishes actual inactivity from active work. Model frames, tool results and real stage transitions renew the existing inactivity budget. Parent-generated waiting notices never renew it. A separate visible `max_task_seconds` setting defaults to 900 seconds and cannot be renewed. Socket waits and selected model names are preserved.
- Incoming model frames, including frames before final answer text, report progress. Logs record first-frame time, model load time, generation time and tokens per second when returned by Ollama.
- Partial model output and already-observed tool evidence survive cancellation, timeout and worker failure. Shutdown stops active workers and marks waiting work cancelled.
- Installer updates include the new web assets, retain source backups and rollback, and recognize a running standalone preview before replacing files. Existing personal configuration and the studio database remain separate from the source update.

## Three added features

1. A live browser console over the original desktop Controller. The desktop button opens it locally; it can submit tasks, show responses and activity, cancel work, edit validated settings and test the selected model. `Live-Preview.cmd` is an alternative host using the same agent with the desktop application closed.
2. Durable task traces with explicit retry and transcript export. `task-traces.sqlite3` stores task state and structured activity. An interrupted task is labeled on restart and never automatically replayed. Desktop and browser exports make task responses reviewable in this conversation. Retry can repeat completed actions and requires reviewing the prior evidence.
3. Private phone access through Tailscale Serve. `Enable-Phone.cmd` checks the local Tailscale connection, configures the exact private hostname and HTTPS proxy, and prints the access key. It does not enable public Funnel. Android acts as a remote console; the Windows computer performs the work and must stay awake. Native Windows/Tailscale behavior still requires your device check.

The API binds only to loopback, requires a random bearer key, checks Host and Origin, limits request size, and serves only its named assets. It has no arbitrary shell endpoint. No new third-party Python dependency is needed. The public domain was not deployed or connected.

## Verification evidence

- Full Python/Qt test suite: 183 checks passed on Linux CPython 3.12 with offscreen Qt. New coverage includes real spawned worker execution through the authenticated preview API, trace persistence/export, validation failures, cancellation with partial output, and separate inactivity/overall limits.
- Long-stream regression: 64.149 seconds, completed successfully, 33 received model frames, original 45-second socket wait, worker inactivity budget reduced to 5 seconds. This used a simulated Ollama HTTP server with the actual NDJSON transport and spawned original Strident worker. It verifies the former cutoff is gone for active streams; it is not a benchmark of your model.
- Real direct commands here: Help 0.1215s, System health 0.3031s, List files 0.1175s, Help and then List files 0.0898s. Each used zero model turns. These measurements describe this execution environment, not your Windows hardware.
- Thirty-second isolated native console idle check: passed, zero tasks, zero Ollama requests, 0.033414 CPU seconds (0.111% of one core).
- Native Qt console rendered with the new controls. Browser JavaScript syntax checked. Package requirements passed compatibility checks.
- Browser rendering verification was not completed. This container has no installed browser executable; the official browser download was unavailable, and the separate cloud browser could not reach the container's loopback service. HTTP/API integration tests passed. Actual browser layout and phone operation remain device checks.

Machine-readable results are in `verification-results.json`. This is not a claim that Windows, real model generation, private mobile access, external accounts, Docker execution or public hosting were tested here.

## Upload inventory

The first batch lacked 40 of the 55 files named in its checksum manifest, including the entire engine and all tests. After the additional engine upload, 30 manifest entries were supplied and 25 remained absent. Every supplied manifest entry matches its old checksum after normalizing Windows line endings. Duplicate pairs were main.py/main(1).py, README.md/README(1).md and verify_app.py/verify_app(1).py.

The files still absent from the upload were:

- `Create-Desktop-Shortcut.cmd`
- `Create-Desktop-Shortcut.ps1`
- `Test-Ollama.cmd`
- `assets/agent.ico`
- `assets/face.png`
- `diagnose_ollama.py`
- `docs/curbsentry.md`
- `docs/verification.md`
- `inspect_directory.py`
- `licenses/PyQt6-6.10.2.txt`
- `licenses/PyQt6-Qt6-6.10.2.txt`
- `licenses/PyQt6-sip-13.12.0.txt`
- `licenses/psutil-7.2.2.txt`
- `licenses/pyaes-1.6.1.txt`
- `licenses/pypdf-6.10.0.txt`
- `tests/test_brain.py`
- `tests/test_core.py`
- `tests/test_curbsentry.py`
- `tests/test_idle.py`
- `tests/test_ollama_fix.py`
- `tests/test_process.py`
- `tests/test_repair.py`
- `tests/test_search_results.py`
- `tests/test_store.py`
- `tests/test_ui.py`

These source/test/helper/license assets were recovered from the newer repository. Its updated PDF dependency uses `licenses/pypdf-6.20.0.txt` rather than the older 6.10.0 license filename. Git metadata uploads describe the repository; they do not provide your running Windows agent settings or model weights.

Still not provided: runtime `config.json`, personal `studio.sqlite3`, actual Windows task and Ollama logs, model weights, hardware results, Tailscale account state, CurbSentry connection configuration and hosting/FTP access. These private/device-specific items are not bundled, invented or replaced.

## Device activation

Use the package's START-HERE instructions to update the actual installed copy, not a different extracted folder. Confirm BUILD 3.3.0 in the window. First run Help, System health and List files. Then refresh installed models and run Test writing model in Settings. If it fails, Check-Strident.cmd writes Downloads/Strident_Diagnostics.json with model and hardware evidence. That evidence is required to finish diagnosing the separate 45-second first-response failure on your PC.

Open Live preview / phone after the desktop tests. Export a transcript to share actual task behavior here. ChatGPT cannot automatically view your local console or control your PC from this session. For Android, run the included private setup and follow docs/live-preview.md. No signed mobile app is produced by this change.

`strident.ai.42web.io` and `promptcopystudio.42web.io` could not be verified from this environment. InfinityFree hosting access was not supplied. The private desktop agent remains on the PC; the public address is not substituted for a running Python/Ollama host. Your original reviewed Gumroad update flow, read-only CurbSentry adapter and constrained coding workflow retain their existing capabilities and requirements.

Primary technical references: [Ollama streaming](https://docs.ollama.com/api/streaming), [Ollama model controls](https://docs.ollama.com/capabilities/thinking), [Ollama performance and loaded-model guidance](https://docs.ollama.com/faq), [Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve), [InfinityFree Python support](https://forum.infinityfree.com/t/does-infintyfree-support-python/117556/3).
