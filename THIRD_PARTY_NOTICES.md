# Third-party dependencies

The installer obtains unmodified official packages through pip. Their binaries are not embedded in this source ZIP. Exact license texts from the tested distributions are included in `licenses/`.

| Package | Pinned version | License in tested distribution |
| --- | --- | --- |
| PyQt6 | 6.10.2 | GNU GPL version 3; Riverbank also offers a commercial license |
| PyQt6-Qt6 | 6.10.2 | GNU LGPL version 3 in the wheel license; Qt components and third-party modules have their own applicable terms |
| PyQt6-sip | 13.12.0 | BSD 2-Clause |
| psutil | 7.2.2 | BSD 3-Clause |
| pypdf | 6.21.1 | BSD 3-Clause |
| pyaes | 1.6.1 | MIT; fixed AES-CBC cookie arithmetic for the configured website |

Python is supplied by your installation and has its own Python Software Foundation license. SQLite and HTTP/JSON functionality are accessed through Python's standard library. No Gumroad SDK or Gumroad server source is copied into this package. The native HTTP client follows API request/response contracts; account permissions, provider terms and available endpoints still apply.

Ollama, model weights, browser software and store services are external and are not bundled or relicensed. Review the license of the exact model you select, especially custom or downloaded weights. Removing a noncommercial upstream application does not change a model's license.

GPL permits commercial use and private company use. PyQt's licensing FAQ distinguishes internal use from distribution under GPL-incompatible terms. The dependency license texts and credits are retained; none are replaced with a blanket claim that all software is owned by Prompt Copy Studio.

Primary references:

- https://www.riverbankcomputing.com/software/pyqt/intro
- https://www.riverbankcomputing.com/commercial/license-faq
- https://www.gnu.org/licenses/gpl-faq.en.html#GPLRequireSourcePostedPublic
- https://www.gnu.org/licenses/gpl-faq.en.html#InternalDistribution
- https://pypi.org/project/PyQt6/6.10.2/
- https://pypi.org/project/PyQt6-Qt6/6.10.2/
- https://pypi.org/project/PyQt6-sip/13.12.0/
- https://pypi.org/project/psutil/7.2.2/
- https://pypi.org/project/pypdf/6.21.1/
- https://gumroad.com/api
- https://docs.ollama.com/api/chat
- https://github.com/ricmoo/pyaes
