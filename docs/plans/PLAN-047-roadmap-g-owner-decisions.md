# PLAN-047: Roadmap step G, the owner's decisions on four product directions (master list RM-G)

Status: done

## Goal
The four items the roadmap audit held back for an owner decision (workflow builder, specialist agent roles, cloud workers, skills marketplace) each have a recorded answer, so the next plan for any of them starts from a decision and not from a guess. This plan records decisions; it builds nothing.

## Scope
In: the four answers below, what each one lets us design next, and what each rules out.
Out: any code. Each "next" line needs its own plan (with the headings in `docs/plans/README.md`) before the first line of code.

## Acceptance
1. Each of the four items has one recorded answer with the date. (Met by the status log below.)
2. `docs/IMPLEMENTATION_TRACKER.md` section 1.25 points here, and master list row RM-G is closed with a pointer.
3. No answer is read as more than it says: the "what it rules out" lines are part of the record.

## Guard tests
None, because this is a decision record with no behaviour. The decisions are enforced by the plans that follow from them.

## Rollback
A later dated line in the status log can change any decision; never edit an old line.

## Status log
- 2026-11-02: the owner's answers (asked as four questions, with a recommendation on each):
  1. **Workflow builder: share as files.** Export a plan or preset as a JSON file and import one, shown as a read-only step list in the dock; every step still runs through today's confirmation, egress and sensitivity gates. Rules out (for now): a node editor. Next: a plan for the file format (it is also the format item 4 needs).
  2. **Specialist agent roles: full team** (the owner chose this over the recommended "not now"). Several roles with their own tool sets and prompts. The audit's caution stands and is recorded with the decision: the benefit is unproven and every role adds model calls per request. So the next step is a design plan, not code, and it must state: which roles; which tools each may call (reuse `tool_operations.py` classes and the MCP allowlists as the starting point); how a role's write calls reach the existing confirmation gates (a role never gets a gate of its own to switch off); how cost per request is measured before and after; and a stop condition (if a measured request costs more than a set multiple of the single-agent cost without a measured gain in correct results, the roles are not shipped). Building the QA role first is the smallest staged start and needs no extra decision.
  3. **Cloud workers / hybrid execution: the plugin stays local.** No remote worker, job protocol or data upload in this codebase. `service/` stays a separate prototype and `providers/cartogen.py` a labelled stub. Consistent with CLAUDE.md (no tier-gating logic here). Rules out: anything in the plugin that sends project data to a service run by us or by a user's own server. Reopen only with a new dated line.
  4. **Skills marketplace: files, no store.** Workflows are shared only as data files (the item 1 format) that contain no code and run through the existing gates; people share them through GitHub or any file transfer. No marketplace, no catalogue, no code in packages. Rules out: executable packages, a signing scheme, an install-from-URL path inside the plugin. Reopen a curated catalogue only after the file format has users.
- 2026-11-02: follow-up plans to write (none started): (a) the shareable workflow file format and its import checks (items 1 and 4 together; import must refuse any step whose tool is not on a stated list, and must show every step before anything runs); (b) the specialist-roles design plan with the measurements and stop condition above.
- 2026-11-02: follow-up (a) is written as `docs/plans/PLAN-048-shareable-workflow-file.md` (status planned, four small decisions for the owner at its end). Follow-up (b), the agent-roles design plan, is not written yet.
