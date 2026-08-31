# Destructive Tools Audit (2026-08-21)

Requested as a follow-up to `docs/ENGINEERING_PRODUCT_UX_REVIEW_2026-08-20.md` §3.2's
recommendation to audit which destructive tools have the preview/confirm safety gate and which
don't, now that the tool registry has grown to 131 tools. Method: grepped every file in
`agent/tools/` for the `PREVIEW_REQUIRED` status string (the gate's actual implementation,
documented in `SECURITY.md` §5), then cross-checked every tool that mutates data already loaded
into the project against that list — file:line references throughout, not assumed from tool
names or descriptions.

## 1. What the gate actually protects

`agent/agent.py`'s `_real_execute_tool` strips any `confirmed` argument the model tries to
inject into its own tool call (`filtered_args`, `agent.py` ~line 253) before dispatch. A gated
tool function checks `confirmed` itself and, if false, returns a `PREVIEW_REQUIRED` payload
instead of running — the only way `confirmed=True` ever reaches the function is a real UI button
click in `ui/dock_widget.py`. This is a code-enforced gate, not a prompt-level instruction (prompt
rule 9 in `agent/prompts.py` tells the model to *announce* the preview, but the model cannot
bypass it even if it ignores that instruction).

Before this audit, exactly two tools implemented it: `remove_layer` and `field_calculator`
(`agent/tools/vector_tools.py`), plus `load_project` (`agent/tools/project_tools.py`, found during
this audit — `SECURITY.md` §5's prose had drifted out of sync with the code, which already had
three gated tools, not two; fixed as part of this round).

## 2. Finding: `calculate_area`/`calculate_length` mutated data in place but weren't gated

**Fixed this round.** `agent/tools/vector_tools.py`'s `calculate_area` (was line 1372) and
`calculate_length` (was line 1380) both called `_add_calculated_field` — the *exact same*
primitive `field_calculator` uses (`layer.startEditing()` → `changeAttributeValue()` per feature
→ `commitChanges()`, mutating the live, already-loaded layer object returned by
`_find_layer_by_name`, not a copy). `field_calculator`'s own tool description already calls this
operation class "Destructive action requiring UI confirmation," and prompt rule 9 already told the
model that "attribute mutations" require confirmation — but only named `field_calculator`, not the
other two functions performing the identical mutation. This was a real inconsistency, not a
judgment call: the codebase had already decided this operation class needs the gate; two of its
three call sites just didn't have it wired up.

Both functions now follow `field_calculator`'s exact pattern (`confirmed: bool = False` parameter,
`PREVIEW_REQUIRED` short-circuit before touching the layer). `agent/prompts.py` rule 9 and
`SECURITY.md` §5 updated to name all five now-gated tools. Two new tests
(`test_destructive_calculate_area_gate`, `test_destructive_calculate_length_gate` in
`tests/test_new_tools.py`) mirror the existing `remove_layer`/`field_calculator` gate tests.

## 3. Finding: four humanitarian analysis tools have the same gap — flagged, not fixed

`agent/tools/analysis_tools.py` has a parallel family of "write results back onto the input
layer" helpers — `_write_scores_to_layer` (line 361), `_write_presence_gap_status_to_layer` (line
396), `_write_population_to_layer` (line 586), `_write_damage_severity_to_layer` (line 749) — each
called, when `output_field` is passed, by `calculate_severity_index` (line 319),
`calculate_presence_gap` (line 480), `calculate_population_in_need` (line 659), and
`calculate_damage_exposure_severity` (line 842) respectively. These use
`provider.changeAttributeValues()` directly rather than `startEditing()`/`commitChanges()`, but
the effect is the same category of action: an in-place attribute mutation on the live,
already-loaded admin-boundary layer, exactly what `field_calculator` is gated for.

**Deliberately not gated this round.** Unlike `calculate_area`/`calculate_length`, these four are
the core, highest-value tools in this plugin's humanitarian workflow — severity index → presence
gap → population-in-need → damage severity is the primary analytical chain the product exists to
support, typically re-run several times as an analyst iterates on indicator fields or weights.
Inserting a UI confirmation click into that chain is a real product/UX tradeoff, not a mechanical
consistency fix, and forcing it unilaterally risks solving a theoretical consistency problem by
creating a real workflow-friction one. Three ways to resolve it, in order of how much they change
today's behavior:

1. **Leave as-is, documented as an accepted gap.** These tools are idempotent (re-running with the
   same `output_field` overwrites the same field, doesn't compound), always explicitly
   user-initiated with a named `output_field`, and the layer stays fully intact and re-runnable if
   the result is wrong — lower real risk than `remove_layer` (data leaves the project) or
   `load_project` (unsaved work is lost).
2. **Gate all four**, for full consistency with `field_calculator`'s stated invariant, accepting
   one extra click per severity-index run as the cost.
3. **Narrow the gate's stated scope** instead of widening it — write prompt rule 9 and
   `field_calculator`'s own description to say the gate exists specifically for
   *irreversible-relative-to-project-state* actions (`remove_layer`, `load_project`) rather than
   "attribute mutations" broadly, and treat `field_calculator` itself as the outlier to reconsider
   rather than the baseline every other write-a-field tool must match.

No option was applied — this needs your call, not mine, since it trades off safety-gate
consistency against friction in the app's core workflow. Recommendation if a default is wanted:
**option 1** (document as accepted, given the idempotency and low real-harm profile), revisited if
a future analyst reports actually losing work because of a mis-typed indicator expression run
through one of these four tools without a chance to preview it first.

## 4. Finding: `execute_pyqgis_script` has no confirmation gate — reviewed, not a gap

`agent/tools/system_tools.py`'s `execute_pyqgis_script` runs model-generated Python immediately,
no `PREVIEW_REQUIRED` step at all — in principle the broadest-scope tool in the registry, since a
script could in theory call `layer.dataProvider().deleteFeatures()` or similar. This looks alarming
in isolation, but `SECURITY.md` §1 already documents this tool's actual protection model: an
AST-based `_validate_script_safety` allowlist plus a restricted-builtins `exec()` sandbox, adversarially
tested against import/eval/attribute-traversal bypasses (see `SECURITY.md`'s before/after testing
table). The confirmation gate and the sandbox are two different mitigation strategies for two
different tool shapes — the gate previews a *specific, named, single mutation* a human can read at
a glance ("field 'pop_density' on layer 'X'"); a script's effects aren't reliably summarizable the
same way, so a confirmation dialog here would show raw source code and effectively train users to
click through without reading it, which is weaker than the sandbox actually restricting what's
possible. Not treated as a finding — already a disclosed, deliberate design choice, not a silent
gap.

## 5. Reviewed, confirmed non-issues

The overwhelming majority of the 131-tool registry follows a "create a new output layer, never
mutate an existing one" pattern via the `_run_and_add`/`_run_raster_and_add` helpers
(`OUTPUT: "memory:"` in the Processing algorithm call) — `buffer_analysis`, `clip_layer`,
`intersect_layers`, `union_layers`, `difference_layers`, `dissolve_layer`, `spatial_join`,
`join_by_attribute`, `merge_layers`, every raster tool in `raster_tools.py`, and more. These are
non-destructive by construction: the source layer(s) are read, never written. Also reviewed and
not flagged:

- **`save_project`** — overwrites the current project file when `output_path` is omitted. This is
  standard "save" semantics (no application asks "are you sure?" before a save), not the same risk
  class as `load_project` (which discards the current in-memory state, including unsaved changes,
  to load something else).
- **`save_workflow_preset`** — silently overwrites an existing preset of the same name. Low
  stakes: a named settings-storage slot, not project data, and immediately re-creatable if
  overwritten by mistake.
- **Styling tools** (`apply_categorized_style`, `apply_graduated_style`, `change_layer_color`,
  `set_layer_transparency`, `set_layer_order`, etc.) — change a layer's renderer/symbology, not its
  underlying feature data. Trivially reversible by re-styling; not in the same category as an
  attribute-table mutation.
- **`toggle_visibility`, `rename_layer`** — cosmetic/metadata changes, not data mutations.

## 6. Summary

| Tool | Mutates live layer in place? | Gated before this round? | Status |
|---|---|---|---|
| `remove_layer` | N/A (removes layer) | Yes | Unchanged |
| `load_project` | N/A (replaces project) | Yes | Unchanged (SECURITY.md §5 now names it) |
| `field_calculator` | Yes | Yes | Unchanged |
| `calculate_area` | Yes | **No** | **Fixed this round** |
| `calculate_length` | Yes | **No** | **Fixed this round** |
| `calculate_severity_index` | Yes (if `output_field` set) | No | Flagged, not fixed — needs a product decision (§3) |
| `calculate_presence_gap` | Yes (if `output_field` set) | No | Flagged, not fixed — needs a product decision (§3) |
| `calculate_population_in_need` | Yes (if `output_field` set) | No | Flagged, not fixed — needs a product decision (§3) |
| `calculate_damage_exposure_severity` | Yes (if `output_field` set) | No | Flagged, not fixed — needs a product decision (§3) |
| `execute_pyqgis_script` | Potentially (arbitrary) | No (sandbox instead) | Reviewed — deliberate, disclosed design (§4) |
| `save_project` | N/A (writes to disk) | No | Reviewed — normal save semantics (§5) |
| `save_workflow_preset` | N/A (settings storage) | No | Reviewed — low stakes (§5) |
| Everything else (~120 tools) | No (creates new layer, or read-only) | N/A | Reviewed — non-destructive by construction (§5) |
