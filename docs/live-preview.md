Historical documentation from the supplied build. For the October 22 repair and account behavior, read repair-report-2026-10-22.md and service-readiness.md.

# Desktop, browser and phone access

Launch the updated desktop application and click **Live preview / phone**. The browser opens a local console authenticated with a random access key. Both interfaces use the existing Controller and its tools, history and task queue. The preview starts only when opened; startup does not call Ollama.

The standalone `Live-Preview.cmd` runs the same agent without Qt. Close the desktop instance first. Keep its terminal open to keep the agent available. Ctrl+C stops it and its active task. The instance lock prevents two independent controllers from writing to the same personal data concurrently.

The console listens only on `127.0.0.1:8765`. Its API requires a bearer key. The initial local browser URL passes the key through a URL fragment, removes that fragment from history, and keeps the key in session storage. Configuration is in the existing `%LOCALAPPDATA%\PromptCopyStudioAgent\config.json`. Do not share that file or its `preview_key`.

## Private phone setup

Close Strident and run `Enable-Phone.cmd` on Windows. The script checks the installed Tailscale CLI, signed-in state and private hostname, backs up configuration to `config-before-phone.json`, adds that exact hostname to the host allowlist, and enables Tailscale Serve HTTPS on port 443. It refuses to replace a detected unrelated Serve configuration. No Tailscale Funnel is enabled. Review any existing Tailscale Serve setup before using the disable command, which turns off its HTTPS 443 listener.

Reopen Strident and click **Live preview / phone**. Connect the phone to the same Tailscale network. Visit the printed private `.ts.net` address, then paste the key printed by setup. Tailnet access controls must permit your phone to reach this PC. Tailscale may ask you to enable HTTPS support for the tailnet. If so, complete that step and rerun setup. The PC must remain awake and both Ollama and Strident must stay available.

To stop private sharing, run `Enable-Phone.cmd --disable`. Closing the preview host also stops agent access. This is a personal local HTTP service behind Tailscale's private HTTPS proxy, not an Internet-facing public API.

## Task records and support

A separate additive `task-traces.sqlite3` database stores queued tasks, received output and activity events. Existing products, memory and drafts remain in `studio.sqlite3`. Interrupted tasks are labeled when the controller next starts; none are replayed automatically. Retry creates a new task and may repeat completed actions, so inspect evidence first.

**Export transcript** works in the desktop and browser interfaces. It includes task text, outputs, local paths and tool results. It excludes the configuration file and its preview key. User-entered secrets can still appear in task text. Review the transcript before uploading it to this conversation. ChatGPT has no automatic live view into your PC; sharing this export is how task responses become available here.

## Your public address

`strident.ai.42web.io` can be a public website address, but it is not the local desktop runtime. No DNS, InfinityFree account, FTP or hosting settings were changed. The public URL could not be verified from this execution environment. Use the private Tailscale URL for this release's phone access. InfinityFree's free hosting does not support a persistent Python/Ollama process.

References: [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve), [Serve CLI](https://tailscale.com/docs/reference/tailscale-cli/serve), [InfinityFree Python hosting support](https://forum.infinityfree.com/t/does-infintyfree-support-python/117556/3).
