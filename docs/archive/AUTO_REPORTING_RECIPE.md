# Auto-Reporting Recipe — Program Update Composition

**Status: Recipe, not a spec.** Composes tools that already exist and ship today
(`schedule_recurring_workflow`, `generate_html_dashboard`, `generate_sector_coverage_report`) --
no new code in this document. The only thing genuinely new here is the composition itself and the
correction below.

## Correction to the original proposal

A gap-analysis review proposed "`schedule_recurring_workflow` + `generate_html_dashboard` +
`generate_sector_coverage_report` already compose into an auto-generated weekly/monthly program
update" as a zero-code recipe. **That's not quite right, checked against the actual code**:
`agent/tools/monitoring_tools.py`'s `_ALLOWED_WORKFLOW_TOOLS` restricts recurring-workflow steps to
7 read-only analysis tools (`calculate_severity_index`, `calculate_presence_gap`,
`calculate_population_in_need`, `forecast_trend`, `field_statistics`, `population_access_gap`,
`estimate_population_exposure`) -- deliberately, per that module's own docstring, so an unattended
recurring run "can't silently repeat a destructive action," which the original design read broadly
enough to exclude any file-writing tool, not just geometry edits. `generate_html_dashboard` and
`generate_sector_coverage_report` both write real files and are **not** on that list --
`save_workflow_preset`-ing a step naming either one, then trying to schedule it, fails with a clear
"Step(s) reference tool(s) not allowed in a recurring workflow" error.

## What's actually free today: automated monitoring, on-demand reporting

The genuinely zero-code recipe:

1. **Save and schedule the analysis** (fully automated, already-allowed tools):
   ```
   save_workflow_preset(
       preset_name="weekly_program_check",
       workflow_json='{"steps": [
           {"tool": "calculate_severity_index", "args": {...}},
           {"tool": "calculate_presence_gap", "args": {...}}
       ]}'
   )
   schedule_recurring_workflow(preset_name="weekly_program_check", interval_minutes=10080)
   ```
   (10080 minutes = 7 days.) This runs unattended for as long as QGIS stays open, posting a change
   summary into chat every tick ("3 units changed severity class since last run") without spending
   an API call, per `agent/tools/monitoring_tools.py`'s existing design.
2. **Generate the dashboard/report on demand**, triggered by reviewing that chat summary: when a
   tick shows a real change worth reporting, ask for `generate_html_dashboard` and/or
   `generate_sector_coverage_report` against the now-current data. This is a human-triggered step,
   not an unattended one -- the human is the one deciding "this change is worth a fresh report,"
   which is also, incidentally, a more useful editorial gate than generating a report on a fixed
   schedule regardless of whether anything actually changed.

This is genuinely "automated monitoring + on-demand reporting," not "fully automated reporting" --
a real difference from the original framing, not a rounding error.

## If fully unattended report generation is actually wanted

That requires deliberately expanding `_ALLOWED_WORKFLOW_TOOLS` to include file-writing tools -- a
real, security-relevant decision (unattended file writes on a schedule, not just unattended
read-only analysis), not something to fold into a "free recipe" doc. Flagged here, not done: if
this is wanted, it needs its own explicit decision and probably its own small spec covering what
"unattended" should mean for a tool that writes a real file to disk every time it fires (where does
it write, does it overwrite the last run's file or version them, what happens if the write fails
mid-schedule) -- questions the existing read-only-tool allowlist never had to answer.

## Prompt guidance (shipped alongside this doc)

`agent/prompts.py` rule 36 teaches the model to recognize "set up a weekly/monthly program update"
intent and map it to this exact two-step recipe (schedule the analysis, generate reports on demand
when a tick shows something worth reporting) -- not to attempt scheduling the dashboard/report
tools directly, which would just fail with the allowlist error above.
