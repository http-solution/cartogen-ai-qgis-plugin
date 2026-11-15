---
description: What happens between sending a request and seeing the answer: matching, prompt building, the tool-calling rounds, guards and the final reply.
---
One request is one **turn**. The dock hands it to `CartogenAi.run()` on a background `QgsTask` thread; `_run_impl` runs the loop. This page follows a turn in order.

## 1. Before the model is called

1. **Task matching (local).** The request is matched against the [task register](@reference/task-register) on your machine; no API call is made. A match yields a *contract*: what information is still missing, which tools the task prefers, and what you should end up with (a styled layer, a CSV, a dashboard, a report). If something genuinely cannot be guessed (which hazard, which facility type) you are asked once. Otherwise a **preview** shows the exact prompt about to be sent and why. Your reply sends it, replaces it with your own wording, or cancels.
2. **Queue.** Several separate requests pasted into one message become a queue of jobs, shown to you and run one at a time after you confirm.
3. **Optional refinement.** If you turned it on (off by default), the prompt refiner sends your message to the same provider once more to propose better-specified candidates. This doubles how often a message leaves your machine.
4. **Tool selection.** `ToolRouter.filter_relevant_tools` offers the model about **40** tools, chosen from the data sources and actions the request names (`capabilities.py`), carrying over tools used in the previous two turns. If a step needs something outside the offered list, the model calls `find_tools`.
5. **System prompt.** `build_system_prompt` assembles the rules, the active task plan, project memory, the map context (layers, CRS, extent), your profile, and, if you turned it on, a Project Inspector snapshot. The layer list goes last so the stable prefix can be cached by the provider.
6. **Chain facts.** If the request names all the steps of a pre-built chain (for example "buffer then clip"), the project is inspected once so the chain's slots can be bound to real layers.

## 2. The rounds

The loop runs up to **20 rounds** by default (settable 1 to 100). The first model call may produce up to the provider's default output size; later rounds half of it. Each round:

1. **Budget check.** The observed tokens so far plus the size of the last call must fit the per-turn token budget (default **450,000**, a provisional figure from hand-test logs; 0 means no limit). A request is stopped *before* a call that would pass it, and the reply reports what finished.
2. **Stop check.** If you pressed Stop, or the project changed under the turn, the loop ends with "[Agent stopped]".
3. **Model call.** Sent through the provider client over QGIS's network stack. Every call is measured (provider-reported input, cached and output tokens, latency, tools offered).
4. **No tool calls?** Then the text is the candidate final answer: it is reconciled with the tool log, checked by the response guard, saved to history and returned. One exception: if the request asked to *see* the result and the model stopped one step short, a single deterministic nudge asks for the styling or zoom call (`look_followup`).
5. **Tool calls.** For each call:
    - the arguments are parsed and validated against the tool's schema; the confirmation flag is stripped from anything the model supplied;
    - the **egress gate**, **plan gate** and **model-view** policy decide whether the call may run or what the model may see of the result;
    - the tool runs ([where it runs](@architecture/threading));
    - the result is annotated if it did not actually run (preview required, waiting for confirmation), recorded in the **transaction log** for best-effort undo, and tagged with **lineage** if it created a layer;
    - the **loop guard** records it.
   `run_steps` lets the model send up to **8** dependent calls in one round trip; they are validated against the project first, run one by one through the same path, and stop at the first error or pending confirmation.
6. **End of round.** The loop guard judges the round. History is compacted if it grew; one-shot nudges may be added (the model keeps guessing file paths; a tool you named was never called; script sandbox errors repeat).

## 3. Ending a turn

| Ending | What you see |
|---|---|
| The model answers | The reply, plus footnotes for anything the response guard could not tie to a tool result, and a delivery note if the task promised an output that was not produced. |
| **Output router** | If you named a deliverable and the step that writes it never ran, **one** follow-up turn asks for it. Never a loop. |
| **Loop guard stop** | `[Agent stopped] …` saying what was done and what was not, and "The request is NOT complete." A read-only turn that had gathered results is first asked once to answer from them. |
| Token budget or round cap | A report of what finished. |
| Stop pressed or project changed | `[Agent stopped]`. A stale turn can no longer deliver a result or act on a different project. |

## 4. After the turn

The reply, its tool steps and a usage footer are shown; the conversation is appended to history (and saved in the project if that setting is on). Optionally, an **evidence folder** records every call's real arguments, results and timings, the layers created, copies of written files with SHA-256, and a canvas screenshot; an **API trace** records every model request and reply. Both are off by default and store raw values.

## Where the code is

| Stage | Module |
|---|---|
| Loop | `core/agent/agent_orchestrator.py` (`run`, `_run_impl`, `_prepare_turn_prompt`) |
| Matching and contracts | `task_matcher.py`, `task_register.py`, `file_io.py`, `output_router.py` |
| Tool choice | `services/tool_router.py`, `capabilities.py`, `discovery.py`, `chains.py`, `step_runner.py` |
| Prompt | `prompts.py`, `map_context.py`, `onboarding_profile.py`, `memory.py` |
| Guards | [Guards and honesty checks](@architecture/guards) |
| Measurement | `call_metrics.py`, `usage_tracker.py`, `api_trace.py`, `evidence.py` |
