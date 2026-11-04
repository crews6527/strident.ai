# Strident.AI 3.3.4 repair

This release fixes a reproduced startup crash in 3.3.3. The desktop entry point called `Qt.ApplicationAttribute.AA_UseHighDpiPixmaps`, which is absent from the pinned PyQt6 6.10.2. Qt 6 handles high-DPI pixmaps automatically. The obsolete call has been removed.

The old tests constructed the window directly and did not run `main.main()`. New regression tests run that entry point with the real Qt window and spawned workers. They check Help, a failed model task, another successful Help task, rendering and clean shutdown. A second flow checks a streamed model reply through a controlled local HTTP fixture. That fixture verifies transport and application integration; it does not run an installed language model.

Settings saved as UTF-8 with a byte-order mark now load consistently with the launch guard. This supports Windows-edited JSON without rewriting the user's file. The command-line Ollama diagnostic now selects the saved writing model, falling back to the task model, matching Settings and `/testmodel`.

The newer GitHub desktop shortcut repair from commit 53a22634d2120c0ed18f8ec9ceba563baa81266b is retained. Model tags, timeout settings and personal data are preserved.

## Windows live acceptance

1. Keep the current installation as a backup. Extract the complete repaired ZIP into a separate folder. Do not move its virtual environment from another folder.
2. Run `Install-Strident.cmd`. Python 3.12 with the Windows launcher is required. Stop if installation reports a failed check.
3. Run `Launch-Strident.cmd` from that folder. Confirm build 3.3.4 in the window. Run `Help` and confirm completion.
4. Start Ollama on the same Windows computer. In Strident Settings, refresh models and select the exact installed model for tasks and writing. Save. For Tony's existing installation, select `qwen3.5:2b` only if it appears in the installed list.
5. Run `/testmodel`. Require a completed reply. Then request `Write one sentence saying hello.` and require a nonempty completed answer.
6. Run `Open Notepad`, then `Open https://example.com`. Confirm the app and page visibly open. A launcher handoff alone is not proof the destination loaded.
7. Stop an active task, then run `Help` again. Close and reopen Strident. It should reopen without a stale instance lock.
8. To test browser accounts separately, run `Live-Test.cmd`, create the initial administrator with the setup key shown in its console, and test administrator and member login/logout. This uses `.live-test` data and its own account database.

Use the newly created desktop shortcut after the new folder passes these checks. Keep the previous folder until then. If generation fails, run `Test-Ollama.cmd` and retain its complete failure message and the Strident transcript. A model timeout, server disconnect or missing model must be investigated on the computer running Ollama; this release does not silently increase wait limits or substitute models.

## Verification scope

Checks run in a fresh CPython 3.12 environment with the complete pinned requirements. Linux Qt tests use the offscreen platform. Windows shortcut execution, Tony's installed Ollama model and phone access require device testing. Passing automated tests does not certify those unobserved paths or promise that every external service request succeeds.

Local verification completed November 3, 2026 (America/Chicago): 218 tests passed in 50.755 seconds; pip dependency check passed; isolated launch guard passed. The five-second idle sample measured 0.010404 CPU seconds with zero submitted tasks and zero Ollama requests.
