---
description: The Humanitarian Mapping Task Register: how the plugin matches your request to one of its tasks locally, and what a task contract contains.
---
The register is a catalogue of **{{tasks}} humanitarian mapping tasks in {{sections}} sections** (rapid mapping, health, WASH, logistics, protection, remote sensing, reporting and so on). Each task is a machine-readable **contract**. When you type a request, the plugin matches it against the register **on your machine**. No API call is made to match, and the register is never sent to the model: it is about 218 KB, so only the one matched task's contract is injected into the prompt.

## What a task contains

| Field | Meaning | Example |
|---|---|---|
| `id` | Section number, a dot, and a stable position | `5.02` |
| `text` | What the task is | "Classify damage by severity" |
| `out` | The **output contract**: what you should end up with | `analysis` |
| `slots` | Information the task cannot proceed without | `aoi` (area of interest), `facility_type`, `threshold`, `time_range`, `hazard_type`, `sector`… |
| `tools` | Suggested tool chain, validated against the live registry: acquisition first, renderer last | `calculate_severity_index`, `apply_humanitarian_look`, `export_to_csv` |
| `kw` | Matching vocabulary | `classify`, `damage`, `severity` |
| `acc` | File kinds the task can take in | `vector`, `raster`, `pdf`, `table`, `image` |
| `prod` | File kinds it can put out | `.csv`, `.pdf`, `.html` |

Output contracts, and what each promises you:

| `out` | You should end up with |
|---|---|
| `layer` | One or more styled QGIS layers on the canvas |
| `layout` | A composed print layout ready to export |
| `dashboard` | An HTML dashboard |
| `report` | A written report with supporting figures |
| `analysis` | Numeric results, a table and a short interpretation |
| `dataset` | An exported dataset or schema, not a rendered map |
| `guidance` | Written guidance or a procedure; no GIS output expected |

## How matching works

Stage 1 is pure local scoring (`task_matcher.py`): tokens of your request against each task's vocabulary, ignoring words that nearly every task contains ("map", "data", "area"…). A match is trusted when it clears a score (0.34) and beats the runner-up by a margin (0.08); otherwise it is *ambiguous* and the request is sent as typed. Failure to match is a normal outcome, never an error.

Rules that came out of hand testing:

- A request that **names a tool** ("Use optimal_hub_siting …") is only matched to a task that uses that tool; otherwise it goes as typed.
- A weak tie across sections (under 25 percent keyword coverage) gives no directive.
- A request that names a loaded layer is not asked "Which facility or service type?".
- A task that names one hazard (drought, extreme heat) matches only when the request names it.

## What you see

1. **Missing information** (a slot with no safe default) is asked once, before anything is sent. Things the plugin can work out itself, such as the area of interest from open layers, are not asked.
2. **The prompt preview**: which task matched and how confident, what you will get, any value assumed on your behalf, and what each attached file will be read as. "yes", "send" or "go ahead" sends it; typing anything else sends your own wording with nothing added; "cancel" abandons it. Previews can be turned off in Settings.
3. **The output check**: after the answer, the tools that actually ran are compared with the contract, and a missing deliverable you named yourself is asked for once. See [Guards](@architecture/guards).

## Honest limits

The register tells the model what to aim for; it does not make the model's analysis correct. A match is a heuristic. Section 36 (engineering hydrology) has a single task. See the [Humanitarian mapping task reference](@humanitarian/task-reference) for the taxonomy behind it.
