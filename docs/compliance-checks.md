# Website compliance request repair

Version 3.2.3 recognizes explicit requests to check, inspect, audit or review a website with several compliance/security/privacy/SEO requirements. The full supplied checklist previously selected model planning: one model call and zero tool calls before the reported 45-second timeout in the reproduced fixture.

The new route starts with public-page inspection and registered product inventory. It performs bounded local product-file checks and saves the full original request, evidence, requested scope and unfinished work as text and JSON. It makes zero Ollama calls, uses no browser-cookie bypass, and keeps collecting local evidence after a website failure. It does not change the selected model, model response timeout, task deadline, account settings or live website.

The website check covers one retrieved HTML page's title, description, headings, mobile metadata, image alt attributes and links. It does not establish deployed CSP/HSTS, database RLS, authentication, privacy compliance, checkout delivery, full WCAG conformance, field INP or mobile-store approval. The catalog is local registrations, not a discovered inventory of every published application or sold file. Each requested checklist line remains unverified unless supported by the stated evidence. Implementation and production verification remain separate tasks.

Local checks attempt at most ten product files, each at most 20 MB, with a 60 MB batch budget and a 25-second between-check budget (smaller for short configured task deadlines). The parent worker deadline remains enforced, including during a slow individual request or PDF parse. Deferred product IDs remain visible. Use `Audit product <id>` to inspect a deferred product separately. Local PDF checks cover page counts, file hashes and existence, not content rights or document accessibility.

Install this package in a new extracted folder with `Install-Strident.cmd`, then use that folder's `Launch-Strident.cmd`. The existing default `%LOCALAPPDATA%\PromptCopyStudioAgent` settings/database remain in use. Keep the previous application folder as a rollback copy. If the older configuration uses a different data directory, that configured location continues to apply. After installation, confirm version 3.2.3 in the window before repeating the checklist.

This source repair was tested on Linux with Python 3.12 and offscreen Qt. Windows installation, native tray behavior and the user's actual Ollama instance require checking on the target computer. General writing/model tasks still depend on Ollama responding; this repair removes that dependency from the recognized inspection request.

Check compliance, /compliance and Run compliance check explicitly select this route. Apply-Strident-Update.cmd repairs the existing installation you choose. General model tasks still require a working Ollama response.
