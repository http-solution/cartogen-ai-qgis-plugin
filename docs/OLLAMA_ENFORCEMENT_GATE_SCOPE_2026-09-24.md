# Cloud-provider egress gate (the "Ollama-only" policy) — scope

**Status: scoping document, PARTLY BUILT (updated 2026-09-24 — see §9).** `SECURITY.md`'s "DPIA determination and
deployment constraints" (2026-09-24) records a DPO determination as *policy*: protection,
incident and displacement data must use local inference; cloud providers are limited to
anonymized, aggregated or macro-level data; raw PII or household-level coordinates must not enter
a cloud context window. `IMPLEMENTATION_TRACKER.md` §1.4 recorded that as document-only, with
technical enforcement deferred. This is the scoping pass for that enforcement. A go-ahead on any
phase below is a separate decision.

## 1. What this can and cannot be

**It prevents accidents, not a determined user.** Any setting this plugin reads lives in
`QgsSettings` on the user's own machine, which that user can edit. A gate here stops an analyst
from *inadvertently* sending protection data to a cloud model; it does not stop someone who wants to
bypass it. Genuine organizational enforcement needs a managed configuration deployed outside the
plugin (a locked QGIS profile / global settings), which is a deployment decision, not code. The
DPO should read this gate as a safeguard in the Art. 32 sense (it reduces the chance of error), not
as a control that removes the need for the organizational SOPs already recorded.

## 2. What exists today (verified in the code, not assumed)

- **A per-layer sensitivity tag exists but is advisory, manual and fail-open.**
  `core/models/sensitivity.py`: levels `PUBLIC/INTERNAL/RESTRICTED/SENSITIVE`, stored as a layer
  custom property. Its own docstring says it is "deliberately advisory, not enforcing", that "no
  automated classification exists", and that a hard block "is a real product decision … this
  module doesn't decide unilaterally." An **untagged layer returns `level=None`**, which nothing
  treats as sensitive.
- **The model can downgrade a tag.** `set_layer_sensitivity` is a normal registered tool with no
  confirmation gate (its parameters are `layer_name, level, reason`). Any enforcement that trusts
  tags must first stop the model changing them.
- **Layer lineage exists.** `core/agent/lineage.py` records each output layer's source layers
  (`tag_layer_lineage(..., source_layers)`, `get_layer_lineage`), so "derived from a sensitive
  layer" is technically available.
- **"Ollama" is not "local".** `OllamaClient(endpoint_url=…)` takes a free-form URL. Selecting the
  Ollama provider and pointing it at a remote host sends data off the machine just the same. The
  gate must classify the *endpoint*, not the provider name.
- **`get_attributes` returns field names only** (`list(layer.fields().names())`), and
  `map_context` carries field names and feature counts, not values. Bulk attribute rows do *not*
  reach the model through those paths. Values reach it through the routes in §3.

## 3. Every route data takes to the provider

| # | Route | Chokepoint | Notes |
|---|---|---|---|
| 1 | **Tool results** | one place: `run()` serializes each result into the `role: "tool"` message (`agent_orchestrator.py`, `json.dumps(tool_result)`) | Arbitrary dict per tool; return shapes vary, so classify by *which layers a call touched*, not by parsing results |
| 2 | **`execute_pyqgis_script` return value** | same serialization point | The hard case: layer names are string literals inside the script, not arguments |
| 3 | **User message text** | chat send path | The user typed it; a warning is appropriate, blocking is not |
| 4 | **File attachments** | `read_attached_file` (`ui/attachments.py`) → user message | Bypasses tools entirely; CSV/XLSX/DOCX/PDF content goes straight into the request |
| 5 | **Prompt refiner** | `prompt_refiner.refine()` calls `client.complete(...)` | A second, separate request to the provider containing the user's text  — **Corrected later the same day:** `build_refinement_messages(query, profile)` sends only the user's own typed text and profile, which the main request sends anyway. No added exposure; no separate gate needed. |
| 6 | **Conversation history** | `conversation_history` re-sent every turn | **Switching provider mid-session re-sends earlier tool results to the new provider.** A gate that only inspects new results misses this  — **Corrected later the same day: this was wrong.** Every write to `conversation_history` stores only the user message and the assistant's final prose (`_append_history(user_message, {"role": "assistant", ...})`), never tool results. What a provider switch carries over is the assistant's own summaries — the "model repeats what it saw" gap in §6, not a separate route. |

## 4. What should trigger the gate — four options

- **G1 — data-class gate: enforce on sensitivity tags** (the existing mechanism), applied to any
  call that touches a tagged layer or a layer derived from one. Matches the DPO's wording (a
  property of the *data*). Weakness: fail-open — an untagged layer is unprotected.
- **G2 — G1 in strict / fail-closed mode:** on a cloud provider, a layer is usable only if
  explicitly tagged `PUBLIC` (or `INTERNAL`); *untagged counts as blocked*. This is the literal
  reading of "cloud restricted to anonymized, aggregated or macro-level data." Cost: every layer
  must be classified first, which is real friction.
- **G3 — tool-class gate:** block a fixed tool set on cloud, reusing the existing
  `_SENSITIVE_CLUSTER_TRIGGER_TOOLS`. Needs no tagging, but blocks harmless uses (buffering a public
  boundary) and misses risky ones (a generic tool run on a protection layer). Not recommended alone.
- **G4 — content detection/redaction on egress** (regex/NER for names, phone numbers, coordinates).
  Unreliable in exactly the cases that matter (transliterated Arabic names, household IDs,
  coordinate precision) and it creates false assurance. Not recommended as the boundary; at most a
  secondary warning.

**Recommendation: G1, with G2 available as an org-level strict switch.** The default behaviour, and
who sets it, is a DPO/Alaa decision (§7).

## 5. Design (if approved)

**Pure logic, new module** `core/models/egress_gate.py`, structured like `plan_gate.py` (Qt-free,
unit-testable): given (provider locality, the layers a call touches, their tags, lineage, mode) →
allow / warn / block, returning a structured result that mirrors the existing
`PREVIEW_REQUIRED` / `PLAN_REQUIRED` shape so the UI and model have one familiar pattern.

**Provider locality**, in the provider layer: classify the endpoint host as loopback / private-LAN
versus public, extending the loopback-only rule `normalize_account_base_url` already applies to the
account URL. A hostname that resolves to a public address is non-local.

**Enforcement points**

1. **Pre-dispatch** in `_real_execute_tool` (the same place as the plan gate): resolve layer-name
   arguments → tags + lineage → block *before* the tool runs.
2. **Result chokepoint** in `run()`: for calls the pre-check could not classify, replace the result
   with a redaction notice rather than sending it.
3. **Attachments** and the **prompt refiner**: gate before the request is built.
4. **History:** on a switch from a local to a non-local provider, either refuse while the history
   contains results from gated layers, or purge/summarize it. Needs a decision.
5. **`set_layer_sensitivity`:** downgrades (toward PUBLIC) must go through the same
   confirm-from-the-UI pattern as other destructive tools; the model must not be able to lower a tag
   itself.
6. **`execute_pyqgis_script`:** the honest options are (a) block on cloud whenever *any* layer in the
   project is non-PUBLIC (safe, coarse), (b) parse layer-name string literals from the script
   (fragile — a script can build names dynamically), or (c) rely on the isolation work in
   `EXECUTE_PYQGIS_SCRIPT_ISOLATION_SCOPE_2026-09-24.md`. Recommend (a) until (c) exists.

## 6. Known gaps this design does not close

- Tag dependence: in non-strict mode an untagged sensitive layer is not protected.
- The model can repeat values it has already seen, including into a later tool argument; the gate
  governs what leaves the machine, not what the model says about it.
- Text the user types or pastes is warned about, not blocked.
- A user who edits the settings, or defeats the locality check by other means, is out of scope (§1).
- A layer a human tags incorrectly stays incorrectly protected.

## 7. Decisions needed before any code (Alaa / DPO)

1. **Default mode:** off / warn / enforce, and whether strict (fail-closed) is the default for a
   deployment that has completed the DPIA sign-off.
2. **Override policy:** can a user lift a block with a recorded justification (as
   `advance_dataset_status(override=True, note=…)` does), and who reviews those records?
3. **Who classifies layers, and how:** manual tagging only, or a prompt at layer-load time?
4. **`execute_pyqgis_script` on cloud:** blanket-block when any non-PUBLIC layer exists, or another
   approach?
5. **History on provider switch:** refuse, purge, or summarize?
6. **Where the policy setting lives** (user settings vs a managed org config), given §1.

## 8. Phased plan (not started)

- **Phase 1 — pure gate + locality classifier + tests.** No behaviour change until wired. Small.
- **Phase 2 — wire pre-dispatch and the result chokepoint; lock down `set_layer_sensitivity`; gate
  attachments and the refiner.** Medium; the risky part is the many tool-argument shapes.
- **Phase 3 — strict mode, layer-classification UX, history handling, override records.** Medium.
- **Phase 4 — live verification** against real QGIS with a real tagged project, including the
  bypass attempts listed in §6 rather than assuming the design holds.

Estimates are relative sizes, not schedules; none has been prototyped.

## 9. What was actually built, 2026-09-24

Built, behind a mode that defaults to **Off** (so nothing changes until someone opts in):
Phase 1 in full, plus the pre-dispatch part of Phase 2 and the `set_layer_sensitivity` lock.

- `core/models/egress_gate.py` — pure logic: endpoint locality classifier, protection rules
  (including the "an explicit PUBLIC/INTERNAL tag on a derived layer overrides inheritance" rule),
  lineage inheritance, argument scanning, the whole-project rule for `execute_pyqgis_script`, and a
  fail-closed decision when the check itself errors in enforce mode.
- Pre-dispatch check in `_real_execute_tool`, so a blocked call never executes.
- Confirmation lock: while the gate is on, lowering a protected tag returns `PREVIEW_REQUIRED`;
  `confirmed` is not in the tool's schema, so a model-supplied `confirmed=True` is discarded.
- Settings → "Cloud data protection" (Off / Warn only / Block) and a strict checkbox.
- 51 new unit tests, and a live run against real QGIS 4.2.2 of 19 scenarios that are bypass
  attempts (block, derived-layer inheritance via real lineage, forged `confirmed`, strict mode,
  `execute_pyqgis_script`, warn, off).

**Defaults chosen without waiting on the §7 decisions**, all reversible: mode Off; strict off; no
override-with-justification flow; the policy setting in user `QgsSettings`.

**Known gap found in review:** lineage stores source layers by name, so renaming or removing a
protected source breaks inheritance for untagged layers derived from it (tag derived layers
explicitly, or use strict mode).

**Not built — still open:** the result-serialization chokepoint (the catch-all for calls whose
arguments do not name the layer), gating attachments and the prompt refiner's separate request,
history handling on a provider switch, a layer-classification UX, and override records. Until those
exist the gate covers the tool-call route only. `EXEMPT_TOOLS` is deliberately just the two
sensitivity tools; other metadata-only tools (styling, zoom, visibility) are blocked on a protected
layer too, which over-blocks but is the safe direction until each is verified individually.

## 10. Second build pass, later on 2026-09-24

Inspecting the remaining routes before building them changed what needed building:

- **Attachments — built.** `ChatInputController.analyze_file` is the single place an attached
  file's content leaves the machine (both the image and the text branch send it; a remembered
  attachment only carries a one-line description on later messages, via
  `task_matcher.compose_user_message`). It is now gated there. A file has no sensitivity tag, so it
  is treated like an untagged layer: blocked on a cloud provider only in **strict** enforce mode
  (warned in strict warn mode), and a blocked file is dropped from the next-message queue.
- **Prompt refiner — no gate needed.** It sends only the user's typed text (§3 row 5, corrected).
- **History on a provider switch — no gate needed for tool results**, because they are never stored
  across turns (§3 row 6, corrected). The assistant's prose summaries do carry over; that is §6's
  existing "model repeats what it saw" gap.
- **Result-serialization catch-all — replaced by a guard test.** A search of all 178 registered tools
  (validated: it matched 176 directly; the other 2 were checked by hand) found that every tool which
  reads feature values names its layer in its arguments, and the only three tools that iterate the
  whole project (`load_project`, `auto_arrange_layer_order`, `get_layers`) read no values. So the
  pre-dispatch check already sees every value-bearing call, with `execute_pyqgis_script` handled by
  the whole-project rule. `tests/test_egress_gate_coverage.py` fails if a future tool reads features
  without naming a layer; it was mutation-checked (a fake unclassifiable tool makes it fail, naming
  the tool). **Limit:** it inspects each tool's own function body, so a tool that reads features only
  inside a helper it calls would not be caught.

Verified: unit suite 2095 passing (58 egress-related tests), and the full live QGIS suite (46
tests) run locally against real QGIS 4.2.2, including 4 new attachment tests that assert the file's
content never reaches the provider (`client.calls == 0`).

**Still open:** the §7 decisions (defaults were chosen reversibly), a layer-classification UX,
override-with-justification records, and — by design — user-typed text and the model's own prose.
