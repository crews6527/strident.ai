# Desktop startup update

The Qt event loop previously aborted the process when a timer or button callback
raised an unhandled Python exception. The outer startup handler cannot catch
those exceptions. The desktop now records the traceback, cancels active and
queued tasks, and displays the exception without aborting. This does not repair
every possible underlying callback error; the displayed exception identifies
what still needs repair. A regression test injects a timer failure and then
completes a real Help task in the same window.

## Windows

Extract the current repository into a new folder. Run Install-Strident.cmd,
then Launch-Strident.cmd. Create-Desktop-Shortcut.cmd points the desktop shortcut
at this installation. Keep the prior folder until the new copy passes live use.
Settings and projects remain in the existing user data folder.

## Mac

Use Python 3.12. In Terminal, change into the extracted repository folder and run:

```bash
bash Install-Strident.command
bash Launch-Strident.command
```

The installer creates a Desktop launcher when the Desktop folder exists.
Launching through it uses this folder's environment, checks package integrity,
and records errors. Keep the extracted folder in place after creating the shortcut.
Windows .cmd and PowerShell scripts cannot be used in Mac Terminal.

## Live acceptance

The installer does not verify model generation. In the opened application:

1. Submit Help and confirm a completed reply.
2. Refresh installed models in Settings and save the exact local model name.
3. Submit /testmodel and confirm a completed generated answer.
4. Submit a short writing request, then another Help command.
5. Close the application and reopen it from the desktop launcher.

Until these pass on the actual computer, the installation is not verified for
personal use. Model tests against a simulated HTTP server only verify protocol
handling; they are not evidence of real Ollama inference.

Errors from the guarded launcher are saved locally in startup-logs under
%LOCALAPPDATA%\PromptCopyStudioAgent on Windows, or
~/PromptCopyStudioAgent on Mac. Review logs before sharing: tracebacks can contain
local paths and service error messages. No diagnostic data is uploaded automatically.
