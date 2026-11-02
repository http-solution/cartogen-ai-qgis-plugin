# PLAN-049: Specialist agent roles, a design with a measured cost and a stop condition (owner decision 2 of PLAN-047)

Status: planned

## Goal
The owner chose "full team" for specialist agent roles (PLAN-047, 2026-11-02) against the recommendation to wait, because the audit's own verdict is "the benefit is unproven" and every role adds model calls. This plan makes that choice safe: it says what a role is in this codebase, which roles, what each may call, how its write calls reach the existing gates, how cost and correctness are measured before anything ships, and the numbers at which a stage is NOT shipped. It builds nothing.

## What exists today (read 2026-11-02)
- **One agent loop** (`agent_orchestrator.CartogenAi`): router picks 9 to 40 tool schemas per request (`tool_router.py`, `find_tools` always appended), a system prompt of about 9,600 tokens whose stable part is cache-friendly, history, then rounds of model call and tools until an answer, a limit or a guard. Measured earlier (IMPLEMENTATION_TRACKER 1.21): every round resends system prompt plus tool schemas plus history; a broad request of six rounds is about 150,000 input tokens before history; all 208 schemas that existed then were about 60,600 tokens together (there are 298 tools now, so more); the router sends about 1,100 tokens for "hello", 4,000 for a precise request, 15,500 for a broad one.
- **Per-call records** (`call_metrics`, `usage_tracker`): tool count, estimated tool tokens, input, output and cached tokens per model call and per turn; the per-turn budget counts cached input at 10 percent. These are the raw numbers the measurement below needs.
- **Gates** that every tool call already passes through `_execute_tool`: write confirmation (PREVIEW_REQUIRED), egress, sensitivity, result gate, undo snapshots, stale-project check, loop guard. `run_steps` and `run_workflow_steps` show the pattern: a different caller, the same gates.
- **Reviewed tool lists** (`tool_lists.py`: READ, WRITE, FETCH) and operation classes (`tool_operations.py`: READ, CREATE, MODIFY, DELETE, PUBLISH).
- **Much of "QA" is already code**, not a model: the result gate, `response_guard` (a failed check the reply leaves out gets a visible warning), the workflow report. This matters for the design (principle 1).

## Principles (each is a rule for the work, with a test where it can be)
1. **A role is a model role only when it needs judgment.** A check that can be code stays code. A role that would only run fixed tools in a fixed order is a workflow, not a role.
2. **A role is configuration, not a new process:** a name, a prompt (a subset of the existing prompt rules plus a short role brief), a tool allowlist, the operation classes it may call, a model tier, and round and token limits. The same loop, the same gates.
3. **No role gets a gate of its own to switch off, and none can skip one.** Every call, from every role, goes through `_execute_tool`. A role cannot send `confirmed`. A PREVIEW_REQUIRED or EGRESS_BLOCKED result stops the whole run and shows the usual card, as `run_steps` does.
4. **Allowlists are enforced at dispatch, not in the prompt.** A call outside a role's list returns NOT_RUN and nothing runs (the MCP policy pattern). `find_tools` inside a role only returns tools in that role's list; a need outside it becomes a handoff request, never a call.
5. **Routing is deterministic first.** The existing router and task matcher choose the role; there is no "manager" model call. A routing mistake costs a handoff, which is measured.
6. **Handoffs are structured data built by code, not prose from the previous model.** Role B receives the user's request plus a record assembled from the turn's tool log and layer lineage (layers made, tools run, settings, checks and their results, what is still to do). It never receives role A's reasoning text. This is cheaper and removes a prompt-injection path (one model's output steering the next).
7. **Off by default, per role, behind a setting.** `cartogen_ai/agent_roles` = `single` (today) | a list of enabled roles. One setting reverts everything.
8. **Attribute every cost to a role.** `call_metrics` records gain a `role` field so a bill can be split.

## Roles, in the order they would be built
| Order | Role | Needs judgment? | May call | Why this order |
|---|---|---|---|---|
| 1 | **QA reviewer** | partly | READ tools, the validators and checks (`diagnose_topology`, `verify_crs_compatibility`, `validate_schema`, `check_pcode_*`, `generate_map_product_qa_checklist`) and the stored result checks; nothing that creates, changes or writes a file (`write_workflow_report` writes a file, so the report is built by code and the role only reads it) | smallest, no new write permission, builds on the result gate. First question the build must answer: how much of it is code. A "role" that turns out to be code is shipped as code and counted as a success of principle 1. |
| 2 | **Cartographer** | yes | styling, labels, layout and export-preparation tools (the largest schemas: this is where per-role tool lists could save the most input tokens), READ tools | the biggest expected token saving; presentation-only writes |
| 3 | **Data scout** | yes | `search_hdx_datasets` (ranked), the fixed-service fetch tools, `find_tools`, READ tools | fetching is the step that went wrong in the Taiz runs; its allowlist is network-facing, so it is built after the two above have proved the mechanism |
| 4 | **Analyst** | yes | analysis tools that create layers (the WRITE list in `tool_lists`), READ tools | the largest and riskiest set; last, and only if the stages before it passed |

Roles 3 and 4 are included because the owner chose "full team", but each is a separate decision point (below): a stage that fails its stop condition ends the sequence.

## Hypotheses the measurement can reject
- **H1 (cost):** shorter role prompts and shorter tool lists cut input tokens per round by more than the extra rounds from handoffs add. Plausible for the Cartographer, unclear for the others.
- **H2 (correctness):** a role with a short brief and few tools picks the right tool more often than one agent with 28 to 40 schemas. PLAN-043 found that most routing misses are vocabulary gaps (49 of 50), which roles do not fix; so H2 is the weakest and the one most worth testing.
- **H3 (safety):** a separate QA step catches errors the single agent states as fact. Partly already tested by the result gate; the question is what a model reviewer adds on top of it.
A null result on all three is an acceptable outcome of this plan.

## Measurement (defined before any run)
**Request set.** At least 20 fixed requests drawn from real owner transcripts and the humanitarian task register, covering short, broad and multi-step requests, 5 of them adversarial (a protected layer, a write that needs Confirm, an instruction hidden in a tool result). Each has a machine-checkable expected outcome where one exists (the tool(s) that must run, a numeric or structural assertion), written before the run. The PLAN-035 runner is the intended tool; until it exists the set is run through the plugin's evidence recorder and scored by hand against the written expectations. The 156 routing rows only test routing and are not this set.

**Arms.** A: today's single agent. B: the same plus the enabled roles. Same provider, same model version, same fixtures, same order, 3 repeats each (model variance is reported, not hidden). That is at least 120 turns per stage.

**Per request, recorded:** model calls; input tokens, cached input tokens, output tokens, and the budget-weighted figure (cached at 10 percent) the plugin already uses; tool calls; wall time; billed cost where the provider reports it; correct or not against the written expectation; any gate bypass.

**Cost of the experiment itself:** the earlier measurement puts a broad request at about 150,000 input tokens, so 120 turns is of the order of 10 to 20 million input tokens per stage. What that costs depends on the provider and its caching. The owner sets the provider and a money ceiling before any run; no run starts without both.

## Stop condition (proposed numbers; the owner may change them before the first run, never after)
A stage ships only if ALL hold on the fixed set, comparing arm B with arm A:
1. **Correctness:** B passes at least as many cases as A (paired by request, medians over the repeats), and a case that passes in A and fails in B is explained.
2. **Cost:** the median budget-weighted input tokens per request in B is at most 1.25 times A, or at most 1.5 times A when B's correctness is at least 10 percentage points higher. Model calls per request at most 1.5 times A.
3. **Time:** median wall time at most 1.5 times A.
4. **Safety:** zero cases where a gate was bypassed or a role called a tool outside its list; the 5 adversarial cases behave exactly as in A.
5. **No regression elsewhere:** the existing offline suite and the live tests pass with the roles setting on and off.
If any fails, that stage is not shipped: its code stays behind the setting, off, or is removed, and the sequence stops. The result and the numbers go in this plan's status log whatever the outcome.

## Scope
In: this design; per stage, its own plan or an update to this one with the role's exact allowlist and brief.
Out: parallel roles, a manager model, roles that talk to each other freely, role-specific models chosen by the user, any change to the gates, a hosted or remote role (PLAN-047 decision 3: the plugin stays local).

## Acceptance (of this plan)
1. The owner has read it and answered the decisions below.
2. Each later stage starts from a status-log line that states its allowlist, brief and the measured result of the stage before.

## Guard tests (to be written with stage 1)
A test that every role's tools exist and that a read-only role lists only READ-class tools; a test that a call outside a role's list returns NOT_RUN and runs nothing; a test that `confirmed` is never forwarded from a role; a test that the roles setting off reproduces today's tool list and prompt byte for byte; a handoff-record test (built from a tool log and lineage, contains no free text from a model).

## Rollback
The setting `cartogen_ai/agent_roles` = `single`. Removing a role's configuration removes the role; nothing else depends on it.

## Decisions needed from the owner
1. **Provider and money ceiling** for the measurement (no run starts without them).
2. **The stop-condition numbers** above, or your own.
3. **Whether a QA step that turns out to be code counts as the first role** (recommended: yes, and it is shipped as code).
4. **Whether the active role is shown in the chat** (recommended: yes, one line per handoff, so a person can see who did what).
5. **Who writes the 20 requests**: you supply real ones (recommended, as for PLAN-043's held-out sets) or I draft them and you review.

## Status log
- 2026-11-02: plan written from the owner's PLAN-047 decision 2 ("full team") and the code and measurements listed above. No code. Nothing has been measured for roles yet; every number about role cost is a proposal or an earlier single-agent measurement.
