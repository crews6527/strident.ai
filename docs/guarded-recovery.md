# Guarded Windows recovery

This package addresses fragile launch and environment recovery. It does not establish that Akido caused an installed failure, and it cannot prevent an administrator or another program with your account's access from changing files.

1. Download and extract this updated source package into a **new folder**, outside the old Strident folder. Keep the old folder as a backup. Do not extract into the Ollama installation, and do not copy an old `.venv` into the new folder.
2. Close Strident normally. Run **Recover-Strident.cmd** in the new folder. It requires installed Python 3.12 and Internet access for pinned dependencies. It creates a dedicated `.venv`; if repairing that folder later, it preserves the old environment and restores it if preflight fails.
3. Run **Launch-Strident.cmd in the new folder**. Existing desktop shortcuts still point to the previous installation until you run Create-Desktop-Shortcut.cmd here.
4. Run `Help`, `System health`, then `List files`. These must finish without a model. Then select an exact installed Ollama model in Settings and run **Test writing model**. A working Ollama server alone is not a passing generation test.
5. For generation, try `Write a short product description for a printable weekly planner.` Check the actual answer. For generated Python projects, use the Coding page and its sandbox check first. Code execution requires the documented Docker setup; chat output alone is not a completed project.

Startup errors are retained under `%LOCALAPPDATA%\PromptCopyStudioAgent\startup-logs`. If the window still does not open, send the newest `.log` from that folder. If generation fails after opening, export the task transcript. Neither a startup preflight nor mocked tests proves your local Ollama can finish a real generation request.

## What the guard does

- Checks distributed file hashes and missing/unexpected Python modules before executing application code.
- Checks exact pinned dependency versions before launch.
- Launches Python in isolated mode, excluding global PYTHONPATH and user site packages.
- Clears conflicting Python and Qt variables **only in the launched process**.
- Records startup exceptions, Qt stderr, and the final process exit code.
- Requires an explicit recovery action; it never downloads an update during normal launch.

It does not kill other applications, disable antivirus, add security exclusions, change system environment variables, alter model settings, erase projects/history, or silently lengthen task deadlines. The checksum file detects accidental drift; it is not a signature that can defeat a malicious application replacing both files and checksums. It checks before launch, not continuously while tasks run.

## Verification limits

Automated checks exercise startup, queue/progress/cancellation handling, model streaming via local test servers, generated-project validation, sandbox orchestration, and file/dependency drift. Windows GUI launch, installed Ollama performance, actual Docker execution and the specific failure on your computer require device evidence. No claim of a finished working local installation is made before those pass.
