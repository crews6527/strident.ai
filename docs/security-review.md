# Dependency security review: October 11, 2026

Strident 3.2.1 updates pypdf from 6.10.0 to 6.20.0. The initial pip-audit report listed 49 vulnerability entries for the older pinned PDF reader, largely involving resource exhaustion from malformed PDFs. The official supported 6.x release keeps the reader API used by Strident. The local audit and compatibility tests cover the pinned Python packages, not every Windows executable, Qt native component, Ollama model, operating-system component or deployment.

After obtaining this release, run the included installer to apply the new requirements in the installed agent's environment. Copying source alone does not update an existing installation. Keep imported PDFs inside the existing bounded worker workflow; a dependency patch does not make arbitrary PDFs trusted. Keep logs and backups private because assistant history may include personal information.

The user-reported Ollama timeout is separate: the selected model did not provide a server response within the configured 45-second wait. This release does not replace the model or silently increase deadlines. Test-Ollama.cmd checks the exact selected installed model directly with a small prompt and bounded deadline. An actual Windows/Ollama run is needed to identify why the user's instance timed out.

Commercial redistribution still requires compliance with PyQt GPL/commercial licensing, model licenses and all included notices. This personal desktop source is not a signed iOS or Android release and has no Apple/Google approval.

Primary references:
- https://pypi.org/project/pypdf/6.20.0/
- https://pypdf.readthedocs.io/en/stable/meta/CHANGELOG.html
- https://riverbankcomputing.com/commercial/license-faq
