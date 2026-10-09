# Cost, routing and missing-capability plan (revised 2026-10-09)

Trigger: a user pasted five humanitarian scenarios (Marib health access, Hadramawt/Al Mahrah district areas, Aden water service gaps, Taizz terrain, coastal-highway
checkpoints) into one chat message; the plugin returned partial answers, identified no usable task or code, and used a lot of API credit. The first diagnosis
(`fixed per-call overhead`, `routing noise`, `missing tools`) was read from code and character counts, not measured. This plan replaces the first draft after review:
it measures before it limits, repairs routing and matching together, treats several scenarios as a queue, and checks existing Processing capability before adding tools.
Release: its own release candidate after the rc22 fixes (rc22 prepared, rc23 = smoke fixes, so **rc24**), chosen from the repository state of 2026-10-09.

## What is proven and what is not
| Claim | Status |
|---|---|
| Each call carries the system prompt and tool schemas | Proven by code (`build_system_prompt`, `filter_relevant_tools`); **size is an estimate** (chars / 4) until step 1 reports provider usage |
| ~26k tokens per call | Estimate. The older smoke footers ("131,878 tokens, 5 calls") are consistent but mix fresh and cached input; the exact split is unknown |
| Credit is consumed by fresh input, cached input and output at different rates | Provider-dependent; step 1 records all three separately |
| The matcher picked a poor task for each scenario | Proven offline (task ids and tool order recorded in the triage) |
| Needed tools were missing from the 40 sent | Proven for the five prompts; **retrieval design** is step 3 |
| Elevation download, contours, line-split do not exist as tools | Proven by registry search; whether Processing already covers them is **checked first** (step 5) |

## Steps (each is its own commit; measurement before limits)
1. **Measure (done in this branch).** `core/agent/call_metrics.py`: one record per model call with model, provider, provider-reported input / cached / output tokens (None when
   not reported, never guessed), latency, tool-call count, the NAMES of the tools sent, and *estimated* prompt parts under an `est_` prefix. Logged metadata-only as
   `model_call`; the chat footer shows observed fresh vs cached input, output and the last call's input. No fixed "each step costs N k" claim anywhere.
2. **Budget and loop controls.** Limits are configurable and provisional (calibrate on successful single scenarios, not guessed). The budget is checked before every request
   against observed usage plus the observed size of the last call. Early stop on repeated failures, duplicate tool calls (same tool and arguments) and no progress
   (several rounds with no new layer, field or file). A stop reports what was done, what was not, and never reads as success; `continue` resumes.
3. **Routing and matching, together.** Derive the needed capabilities from the request (data source, action, available layers), rank tools by name and capability before
   description words, and when the model names a missing step retrieve more tools instead of fixing the list size in advance. Prefer constrained Processing tools; a script
   fallback records its code and runs with validation and limits. Compare tool sets on all five scenarios and on the 120-row smoke prompts before changing the default.
4. **Several scenarios as a queue.** Detect explicit numbered or separated jobs first, show the proposed split for editing, run each job with its own budget and status.
   Several places or datasets can belong to ONE analysis, so a sentence count alone never splits a request.
5. **Verified capability gaps.** Check existing Processing algorithms first (`gdal:contour`, `native:splitwithlines`, `native:difference`, `native:dissolve` ...), then add thin
   wrappers only where a step is genuinely missing. Before choosing a terrain source verify coverage, resolution, licence, availability and reproducibility; record the
   DEM source, resolution and date in the output. A contour interval is not terrain accuracy and must not be reported as such. Highway output defines two results:
   **total uncovered length** and **longest continuous uncovered segment**.
6. **Fewer model round trips.** For predictable workflows, one request produces a validated execution plan, the supported local steps run without further model calls, and a
   compact result goes back; later calls are reserved for decisions, unexpected results and recovery.

## Acceptance (release candidate rc24)
Run each of the five scenarios separately, then the combined queue. Record the full input, tools selected, outputs, failures and usage; independently check geometry and
measurements (areas, lengths, contour count, class areas). A budget stop must report partial completion. Nothing here is hand-tested until that run.
