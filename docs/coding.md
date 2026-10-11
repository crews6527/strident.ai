# Coding and sandboxed tests

Open **Coding** in Strident. Enter a project name and a task such as:

> Write a CSV expense summary grouped by category. Test empty input, invalid amounts and normal totals.

Select **Write, test and repair**. Strident asks your selected Ollama model for a complete Python project and unittest tests, saves a new revision, and executes its tests in a restricted Docker container. If tests fail, it sends the failure evidence back to the same model and can try two repairs. It stops after three attempts, cancellation, its configured task deadline, or a sandbox/model error.

## Set up on your Windows computer

1. Install and start [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/) using Linux containers. Check Docker's requirements for your computer.
2. Open a terminal and run `docker --context default pull python:3.12-slim` once. Strident requires the default local Docker context. It never installs Docker or downloads images automatically.
3. Select an exact installed Ollama model in Strident Settings. The coding workflow uses that model, including models without tool calling. Its ability to write useful code still needs a real task check.
4. Open **Coding**, select **Check sandbox**, then create a small project. Inspect the saved source and actual test output.

The Coding page exposes an output-token budget and a task deadline of 180 seconds by default. These apply only to the submitted coding task; ordinary task settings stay unchanged. Model response timeout and context size remain the values in Settings. Increase the context size for larger projects or split the request when Strident reports insufficient space. Incomplete token-limited output is rejected instead of saved as working code.

Console equivalents are `sandbox status`, `/code project-name describe the task` and `/testcode project-name`. Console requests use the usual task/token settings. Retesting saved code does not invoke the model. File attachments are not automatically imported into coding projects; this release edits its own saved project revisions.

## What is saved

Each complete revision goes under `<workspace>/Coding/<project>/revisions/<revision>/source/`. A completed test run writes `test-report.json` alongside that source folder. Old revisions are retained. Interrupted source writes are ignored when finding the latest revision. After cancellation, saved source and already observed evidence remain available; a test report may be absent if testing was interrupted.

Copy the workspace's **Coding** folder to your backup drive along with the application ZIP and personal data described in README.md. Generated projects are user data and are excluded from the application repository and release ZIP. There is no automatic publishing, GitHub push, dependency installation, replacement of Strident's own source, or deployment of generated projects.

## Scope and isolation

This version supports Python 3.12 standard-library projects with at most 20 complete files and 64 KB of source. Allowed file types are `.py`, `.md`, `.txt` and `.json`. Projects must include `tests/test_*.py`. An empty or entirely skipped suite does not count as passing. A passing generated test suite is evidence of that suite's results, not independent proof that all requirements or security properties are correct. Review the implementation and tests before using the project.

Generated code runs only in a Docker Linux container. The host does not execute it. Strident sends source through standard input without mounting host folders, credentials or the Docker socket. The container has no network, no Linux capabilities or new privileges, a read-only root filesystem, an unprivileged user, one CPU, 256 MB of memory, a 64-process limit and a bounded temporary filesystem. Each test invocation has a 20-second supervisor deadline and a 30-second host wait limit. Captured test output is capped at 12 KB and truncation is marked. The exact local image ID is recorded in test evidence. Docker's own daemon is a privileged service; container isolation is not a virtual-machine security guarantee.

Strident removes its named container after each test invocation and checks removal after worker completion, cancellation or timeout. It also stops owned Docker client subprocesses when ending a coding worker. Cleanup failure is reported visibly. If Strident or Docker crashes, inspect Docker Desktop for containers named `strident-code-*` and remove any remaining ones. No sandbox engine is started while Strident is idle.

Docker is a separate dependency and must be working before generation starts. Missing Docker, a Windows-container engine, a missing image or rejected isolation flags produce an actionable error. There is no fallback to unrestricted local execution. Dependencies needing pip, external services, desktop GUI automation or internet access require a later sandbox extension.

## Verification limits

The application tests exercise source validation, path boundaries, symbolic-link rejection, immutable revisions, empty/skipped suites, container command restrictions, output/deadline handling, fail-closed behavior, repair evidence and cleanup. Docker responses and Ollama generation are simulated in these checks. The supervisor is exercised separately with fixed trusted fixtures for passing/failing tests, bounded output and timeout behavior; this does not establish container isolation. The cancellation test uses a real spawned worker and owned subprocess.

Docker is unavailable in the development environment, so actual container startup, isolation behavior, a real coding-model session and Docker Desktop on Windows have not been verified here. **Check sandbox** checks the engine and image; the first actual project test establishes whether your computer can execute the container. Do that before relying on this workflow for daily use.
