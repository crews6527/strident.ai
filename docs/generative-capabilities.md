# Generative capabilities in 3.3.2

Strident uses an installed Ollama model for inference. Its neural network was
trained before installation; Strident does not train that network, change its
weights, or learn permanently from each task. Explicit saved memories are
retrieved reference text. They are not model training or permission grants.

## Creation and agent workflows

In the task box, enter `/create` followed by a request for text, explanations,
stories, code, website source, experience designs, documentation, research
synthesis, analysis of supplied figures, or marketing and sales-system designs.
This route uses the configured output budget, without the short writing route's
192-token cap. It returns text; it does not save website files, deploy sites,
run generated code, retrieve sources, calculate independently or publish content.
Use the existing `/code project-name ...` route for saved Python projects and
Docker testing, and existing search/read/audit tools for evidence collection.

Use `/team` followed by a request, or `/role team`, for four separate sequential
calls: planner, creator, reviewer, editor. They share the selected local model
and pass bounded drafts between stages. This is an orchestrated workflow, not
four separately trained neural networks. Intermediate drafts appear in tool
evidence and the final edit appears as the answer. Failed stages preserve prior
work. Output truncation stops the sequence; clipped references or handoffs
produce a needs-attention result. Context budgeting estimates characters, not
exact model tokens. Increase context in Settings for longer briefs; actual model
and hardware limits still apply. The current request is never silently shortened.

Every stage receives permanent policy. No stage can call tools or grant itself
host permissions. Administrator attachments can be included as bounded reference
text; member workflows never read host attachments. Normal action tasks retain
the existing tool validation and task supervisor. Cancellation, inactivity and
overall deadlines remain in force. There is no background training or inference
while idle, no recursive delegation and no automatic publishing.

Examples:

- `/create Write a short story about a mechanic restoring a family boat.`
- `/create Draft accessible HTML and CSS for a cleaning-service landing page.`
- `/team Design an opt-in sales system for a digital download, including offers, email drafts, measurement formulas and experiments. Label assumptions.`
- `/team Review these supplied sales figures, show calculation steps and identify missing data: ...`
- `/capabilities` lists supported workflows and dependencies without a model call.

Current product research needs real sources collected with the existing web tools
or supplied as reference. Generated analytics need actual data and checked
calculations. Model review is not independent verification. Virality, revenue,
legal compliance, security certification and store approval are not guaranteed.
Large datasets need ingestion and retrieval infrastructure beyond this bounded
text workflow. Generated source is not a deployed website or a tested experience.

## Local image service

The administrator can connect an AUTOMATIC1111 Stable Diffusion WebUI-compatible
API. This is a separate installation with its own model, hardware requirements,
dependencies and licenses. Strident does not install it, download models, launch
it or change its settings. Keep its Python environment separate from Strident.
The service is not assumed to be present merely because this adapter is installed.

Official setup: https://github.com/AUTOMATIC1111/stable-diffusion-webui
API documentation: https://github.com/AUTOMATIC1111/stable-diffusion-webui/wiki/API
The running service's `/docs` describes the installed version's actual API.

Start the service with `--api`, on loopback, with a compatible image model loaded.
In Strident's browser Settings, set Local image API address. The default is
`http://127.0.0.1:7860`. Only literal loopback HTTP addresses are accepted;
redirects, external addresses and credentials in URLs are rejected.

1. Run `/image-status` to check the endpoint and its model list. This does not
   generate an image or prove that a listed model can run.
2. Run `/image A watercolor illustration of a tidy home office in morning light`.
3. Inspect the returned PNG path under the configured workspace's `Generated`
   directory. The adapter requests one image at 512x512 and 20 steps. It expects
   a base64 PNG response and reports failures instead of claiming success.

Image generation is administrator-only. Requests are bounded by the configured
model socket wait and worker task limits. A timeout does not retry the request.
Cancelling Strident stops its wait, but the independent image service may
continue generating. Stop it through its own interface when necessary. The
adapter does not interrupt unrelated image-service jobs. Image generation can
compete with Ollama for GPU memory; tasks inside Strident run sequentially.

## Verification limits

Automated tests cover stage ordering, handoffs, policy delivery, tool rejection,
member isolation, truncation and partial failures. A local HTTP fixture checks
image API requests, response saving and redirect rejection. A fixture image is
not real diffusion-model generation. Windows startup, actual Ollama generation,
image-service installation, generated-image quality and performance require
live testing on the target PC. Earlier local Ollama missing-runner and invalid
origin errors are not repaired by this capability update.
