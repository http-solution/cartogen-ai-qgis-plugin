---
description: The code-level checks that keep the assistant from inventing results, acting without consent, looping, or leaking protected data.
---
A language model can answer confidently with things that did not happen. Prompt rules alone do not stop that (the first hand tests showed it), so Cartogen AI adds **deterministic, code-level checks**. Each is small, pure where possible, and unit-tested without a model. None is a second AI; none is a guarantee. They narrow what can go wrong and make the rest visible.

## Overview

| Guard | Module | What it prevents | Default |
|---|---|---|---|
| **Loop guard** | `loop_guard.py` | A stuck turn burning every round. | On |
| **Token budget** | `loop_guard.budget_exceeded`, `agent_orchestrator.py` | A request that costs more than a limit. | On (450,000) |
| **Response guard** | `services/response_guard.py` and the reconcile/guard steps in the orchestrator | Presenting output of a call that did not run; unbacked data tables; identifiers, figures and style claims no tool returned. | On |
| **Output router** | `output_router.py` | Promising a dashboard, export or layer and not producing it. | On |
| **Destructive-action gate** | tool dispatcher | The model approving its own destructive call. | On |
| **Stray-fragment gate** | `agent_orchestrator._is_stray_fragment_turn` | A pasted fragment like `template: access_map` creating or deleting anything. | On |
| **Plan gate** | `models/plan_gate.py` | DELETE and PUBLISH calls without a validated plan. | **Off** |
| **Egress gate** | `models/egress_gate.py` | Protected layer data reaching a cloud provider. | **Off** |
| **Model view** | `models/model_view.py` | A protected layer's field names reaching a cloud model. | Follows the egress gate |
| **Nudges** | orchestrator, `look_followup.py` | The model guessing file paths; naming a tool and never calling it; repeating sandbox errors; stopping one step short of the map. | On, each fires once |

## Loop guard

Pure; no Qt or QGIS. It watches three signs of a stuck turn without any model call:

- the **same tool with the same arguments** again (3 times; bookkeeping tools such as `update_task`, `create_plan`, `get_layers` are exempt);
- a tool that **keeps failing** (3 in a row, or 8 failures in a turn);
- **six rounds in a row with no state-changing success** (nothing created, modified, deleted or published).

A stop always reports what was done and what was not, begins with `[Agent stopped]`, and ends "The request is NOT complete" so it cannot read as success. A turn that only *reads* (a web search, an inspection) never changes anything, so before rc35 it was stopped after six rounds with nothing summarised. Now, if such a stall had gathered results, the model is released **once** for a tool-free round with the instruction to answer from the results: say what it found, name the sources it actually received and say what it could not find or verify. A second stall is final.

Two related nudges: after two consecutive "file not found" errors the model is told once to stop guessing paths and use one you gave or a tool returned; and if you named a tool and four other calls passed without it being called, it is reminded once.

## Response guard and reconcile

- A tool result that means *this call did not run* (`PREVIEW_REQUIRED`, `EGRESS_BLOCKED`) gets an explicit note in the data the model reasons over: do not state or invent what it would have returned.
- If a turn ends with a call pending or failed and the answer still contains a data table of three or more rows, a visible warning is appended.
- The final text is **reconciled with the tool log**: a failure the answer does not acknowledge is appended as a correction.
- Replies are **footnoted** when they name an identifier no tool returned (a "District_4" that was never in the data), give a total, mean or preliminary figure matching no tool result, or say a style was applied when no styling call succeeded.
- Replies can create only four kinds of internal link (action, export, prompt, zoom); a file link opens only an existing file of a type the tools write.

These are **wording checks, not a fix for the model inventing values**. They exist because a real hand test showed a sensitive layer blocked by the egress gate while the assistant answered three times with a table of records that did not exist.

## Output router

`task_matcher` turns a request into a **contract**: what you should end up with. After the turn, `output_router.satisfied` compares the contract with the tools that actually ran. A layer contract counts as met by anything that puts a layer on the canvas (a prefix list such as `add_`, `create_`, `fetch_`, `load_`, plus `find_incident_reports`; the missing `find_` prefix once produced a false "step did not run" note). If the promised output is missing **and you named it yourself**, one follow-up asks for it. A task *match* alone never owes you an output.

The follow-up for a missing layer says: call a layer-creating tool if real data exists; if every source returned nothing, **do not invent, sample, simulate or illustrate records**, say which sources were tried and what each returned, and that no layer was made. Earlier wording asked the model to "generate an operational/representative sample dataset"; in a hand test the model then put four invented incidents on the map. A test fails if that wording returns. What still does *not* exist is a guard against the model adding invented points by another route (for example `add_point_layer` with coordinates it made up).

## Destructive-action gate

`confirmed` is stripped from model-supplied arguments, so only a UI click can approve `remove_layer`, `load_project`, `field_calculator`, `calculate_area` or `calculate_length`. The confirmation card names the operation and its target, and a destructive confirmation needs explicit words (a polite "yes please" confirms a *task* card; it does not confirm a destruction). Previews expire when stale. Exports over a file the plugin did not write ask first.

## Plan gate (opt-in)

Gates only DELETE and PUBLISH calls (by operation type). It reuses the existing `create_plan` tool as "the plan", so there is nothing new for the model to learn. Off by default; whether it helps or only adds friction has not been evaluated with a live model.

## Egress gate and model view (opt-in)

When the selected provider is **not local** and a tool call touches a layer tagged protected (RESTRICTED or SENSITIVE, or untagged in strict mode), the call is blocked, or in warn mode allowed with a warning. In enforce mode the **model view** also withholds that layer's *field names* (name, type, CRS and feature count stay visible, because tools address layers by name). Lineage means a layer derived from a protected one stays protected. File attachments pass the same check. Layer tags can only be changed by you, in the Layer Data Sensitivity dialog, never by the model.

This prevents **accidents**. The mode lives in `QgsSettings` on your own machine, which you can edit, so it does not stop someone who means to bypass it; real organisational enforcement needs managed configuration outside the plugin. It does not cover the model repeating in prose what it saw earlier, or text you type or paste. See [What leaves your machine](@security/privacy).

## Scheduled-workflow limits

Allow-list of tools, 1-minute floor, 5 concurrent schedules, and the same cloud-override as running a workflow, because each tick posts results into the chat the model reads next. See [Security overview](@security/overview).

## What these guards do not do

They cannot make the model correct. A convincing answer with a layer on the map is still unverified until you check it: the guards catch a mismatch between what was said and what ran, not a plausible-looking wrong analysis. The rc37 hand test also showed the limits: one fabrication got through until the follow-up wording that invited it was changed. See [Status and open work](@project/status).
