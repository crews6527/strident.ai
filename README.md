# Strident.AI

Strident is a Windows desktop assistant for Prompt Copy Studio. It uses Python 3.12, PyQt6 and a locally installed Ollama model. Version 3.2.3 logs the actual build, local source folder and selected route before every task. Check compliance explicitly runs available website/product checks without Ollama. Startup does not automatically download or synchronize GitHub source. It retains the 3.2.1 PDF dependency patch and the Coding page. Direct website commands and polite basic commands continue to bypass model inference. Browser handoff is reported separately from verified page rendering. The cleaned source excludes old release files, duplicate uploads and bundled development environments.

## Install and launch

1. Download or clone the repository into a folder on your Windows computer.
2. Install Python 3.12, 64-bit, with the Windows `py` launcher.
3. Run `Install-Strident.cmd`. It creates `.venv`, installs the pinned dependencies, runs application checks using temporary test data and creates a desktop shortcut.
4. Open the **Strident.AI** desktop shortcut or run `Launch-Strident.cmd`.
5. In Settings, choose your workspace and an exact installed Ollama model. Use **Test writing model** to check the model before saving your choice. `Configure-Fast-Writing.cmd` can also test a small model already installed on your computer.

Keep the project folder in place after creating the shortcut. Run `Create-Desktop-Shortcut.cmd` if you later move the project. Dependencies need internet access during installation. Ollama and model weights are installed separately.

## Available workflows

- Read a public website, audit page metadata, check a bounded set of same-site links and save reports.
- Register local product files, check PDF page counts, write listing drafts and export reviewed listings.
- Read connected Gumroad products and review a description change before submitting it through the Store page.
- Read a local Instagram content queue and prepare files for manual upload.
- Save confirmed memory, inspect task evidence and cancel active work.
- Open registered Windows applications and hand off URLs to your browser.
- Monitor a separately installed CurbSentry service through an optional read-only adapter.
- Write small Python projects, save each revision, run isolated tests and attempt bounded repairs from test evidence. See [Coding setup](docs/coding.md).

Try `Help`, `Open Notepad`, `Read my website`, `Check my website`, `List files`, `Show my products` or `System health`. These direct commands do not need model inference. Writing and more complex requests use your selected local model.

Long requests to inspect a website for several security, privacy, SEO or compliance items now use a bounded check route with no Ollama request. The original request, public-page evidence, registered local product checks and remaining work are saved under `workspace/website_reports/compliance-*/`. A blocked website does not prevent the product checks. Up to ten local files are attempted, with 20 MB per-file and 60 MB batch limits; deferred product IDs are listed for separate checks. The task remains `needs_attention` because source implementation, hosting changes, legal review and store approval are separate work. See [compliance check scope](docs/compliance-checks.md).

The website address is configured in Settings. Page reports and listing exports are saved locally. This desktop application has no hosting upload adapter, hosted chat endpoint, live Ring camera connection or background microphone capture. It does not publish website changes automatically. **Keep in tray** keeps it available while Windows is running and awake.

## Personal data and backup

The downloadable source ZIP backs up this application version. It does not contain your personal settings, memory, products, recordings or model weights, because those were not supplied as application source.

Close Strident before copying `%LOCALAPPDATA%\PromptCopyStudioAgent` to your backup drive. That default folder contains `config.json` and `studio.sqlite3`, including saved memory, history, product records and drafts. If you changed the data directory in configuration, back up that directory instead. Also copy your configured workspace and actual product files, which remain at their selected paths.

To restore on another Windows computer, extract the source ZIP and run `Install-Strident.cmd`. With Strident closed, restore your personal data to its configured location, restore the workspace/product files and adjust changed paths in Settings. Install Ollama and the selected model separately. Protect backups containing personal data or account connection keys.

Do not commit configuration files, databases, account tokens, CurbSentry connection keys or customer files. A Gumroad token is held only for the current application session. CurbSentry and its recordings are separate from this repository. See [CurbSentry connection](docs/curbsentry.md).

## Checks and troubleshooting

The installer runs `verify_app.py`, which isolates the tests from your personal data. To run it again:

```powershell
.\.venv\Scripts\python.exe .\verify_app.py
```

Run `Test-Ollama.cmd` to test the configured model with a short, bounded request. An Ollama server responding to a version check does not establish that its selected model can generate a reply.

Run `Verify-Idle.cmd` for a thirty-second console CPU sample. It uses temporary app data, blocks and counts attempted Ollama requests, and reports only the console process. It does not measure microphone hardware or other processes. `inspect_directory.py` inventories this project by default and writes reports without moving or deleting inspected files.

[Verification](docs/verification.md) records the checks performed on this cleaned source and their limits. Windows shortcuts, tray behavior, actual model speed and live account operations still require checks on the Windows computer.

## Source and licenses

The source was assembled from the Strident component of the supplied repaired package. Older standalone modules, legacy archiving tools, historical benchmark output, unused artwork, screenshots and the separate storefront/CurbSentry applications are excluded. Data-format imports remain for compatibility. No new upstream authorship comparison or legal clearance was performed.

Application source is covered by [LICENSE.md](LICENSE.md). Dependencies have their own licenses in `licenses/` and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). The active portrait and shortcut icon use supplied Strident artwork, which has separate ownership terms under LICENSE.md.

## Update the existing installation

Extract the package separately, close Strident including its tray instance, run Apply-Strident-Update.cmd and select the existing folder containing main.py and .venv. The updater backs up source, verifies the installed copy and rolls source back on failure. Settings and databases are excluded; installed pip dependencies are not rolled back. Launch the selected folder and confirm Strident.AI 3.2.3 in the title. Desktop shortcuts now include the version.

Check-Strident.cmd saves Downloads/Strident_Diagnostics.json with actual build/route evidence and a bounded text-only test of the exact selected model. Use --offline for no model calls or --command-file path.txt to inspect a supplied task route. The task text/history and keys are omitted from the diagnostic.
