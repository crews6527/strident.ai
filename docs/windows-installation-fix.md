# Windows installation correction: 3.3.1

The Windows log supplied on October 15 shows that version 3.3.0 did not pass installation verification. It ran 183 tests with 11 errors, then restored the previous source. The PDF dependency update remained installed, as the updater reported. This is an installation failure, not evidence from a real Ollama task.

Two defects caused those errors:

- The new trace store used SQLite connections as transaction context managers but never explicitly closed the connections. Windows kept `task-traces.sqlite3` open and refused temporary-folder cleanup with WinError 32. All trace operations now commit or roll back within a context and close their connection in `finally`, including failed operations.
- The instance lock read its first byte before obtaining the Windows byte-range lock. A second attempted instance encountered a raw permission error during that read, outside the cleanup handler, leaving another descriptor open. Acquisition now happens first, even for an empty file. Every failed acquisition or initialization closes its descriptor. Release also closes the descriptor if unlocking raises an error.

The six new regression checks retain database connection references deliberately, so garbage collection cannot hide leaked handles on Linux. They also check rollback, contention before reads, initialization errors, unlock errors, and immediate lock-file reuse/deletion. Native Windows verification runs the entire suite, including the real Windows locking and file-deletion paths.

The browser settings save also preserves the separately selected writing model. An activity response for an old task is discarded after the user changes selection. Browser numeric controls and version-confirmation messages match the backend and delivered version.

The test font warning and the aborted socket in a deliberately timed-out simulated-server test did not cause the reported installation failure. No antivirus changes, elevated administrator run, manual database deletion or test bypass is part of this correction.

## Install the corrected version

Extract the 3.3.1 ZIP fully into a new folder. Close Strident and any standalone preview, then run `Apply-Strident-Update.cmd` from that new folder. Select the existing installation you used before, `C:\Users\crews\Downloads\strident.ai`. The failed 3.3.0 update already restored its prior source, so do not manually restore or delete personal files. The new updater retains the backup and rollback checks.

After verification succeeds, open `Launch-Strident.cmd` in the existing installation and confirm BUILD 3.3.1. Test Help, System health and List files, then run the real writing-model check. This installation correction does not establish that the separate Ollama first-response timeout is fixed on your PC. Private Tailscale/phone activation and public hosting remain separate device/account checks.

References: [Python SQLite connection contexts](https://docs.python.org/3.12/library/sqlite3.html#how-to-use-the-connection-context-manager), [Windows byte-range locking](https://docs.python.org/3.12/library/msvcrt.html#msvcrt.locking).
