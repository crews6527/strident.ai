# Strident.AI development

This is a Python 3.12 desktop application using PyQt6. The entry point is `main.py`. Node tooling is not part of the new core; future Ring integration must remain an explicit adapter.

- Keep runtime settings in `pcs_agent/config.py` and one user configuration file.
- Never import legacy main modules on startup or initialize inference/audio while idle.
- Keep UI changes on the Qt thread via signals; avoid overriding inherited Qt event methods inadvertently.
- Route unambiguous direct commands before model inference. Preserve full commands containing several actions.
- Validate tool arguments. Keep launcher handoff, verified window, browser handoff and page retrieval claims distinct.
- Preserve evidence on failure/cancellation. Stop active workers and do not quietly remap model names or inflate timeouts.
- Keep imports and requirements synchronized. Use the complete pinned dependency set.
- Run `python -m unittest discover -s tests -v` after changes affecting execution or UI flow.
- Run `python verify_idle.py` after changes affecting timers, background threads or startup.
- Add integrations only after their source, credentials location and actual operating system behavior have been verified.
