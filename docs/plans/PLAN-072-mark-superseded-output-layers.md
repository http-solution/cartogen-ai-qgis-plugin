# PLAN-072: Output layers that pile up under the same name are marked superseded (HU-5 part 3)

Status: in progress

## Goal
Owner decision 2026-11-09 ("go with mark superseded for HU-5"): when a tool is run again and produces a layer with the name of its own earlier result, keep the earlier one, renamed, and give the name to the new one. Before this, `QgsProject.addMapLayer()` left two layers with one name, and a later tool that looks a layer up by name could reach the old one. Of the three options (replace, group, mark superseded) the other two were rejected: replace silently destroys the earlier result, group changes the layer tree users rely on.

## Scope
- New `core/agent/superseded.py` (pure helpers plus one function that renames) called from the one hook that runs after every successful tool on the main dispatch path, `agent_orchestrator._tag_created_layers`.
- The earlier layer is renamed `<name> (superseded)` (numbered if taken), gets the property `cartogen_ai/superseded_by` (the new layer's id) and keeps its id, lineage, sensitivity and source records. Nothing is deleted or moved. The tool result gains `superseded_layers` and `superseded_note`, so the reply says what happened.
- Narrow on purpose: only a layer whose own lineage says the same tool made it; never a layer the user made, another tool's output, or a layer a loading tool (`add_*`, `load_*`, `import_*`, `create_empty*`) added.
- Same hook, one fix: it tagged lineage on `mapLayersByName(created)[:1]`, the first layer of that name, which with duplicate names could be the old one. It now picks the layer this call made (`pick_new_layer`).
- Switch: the QgsSettings value `cartogen_ai/mark_superseded = false` turns it off (on by default, like the result gate). No settings-window control.

## Not done, said plainly
- The two-phase fetch tools (network tools) are not covered: that path does not know which layers existed before the call. They keep the old behaviour.
- The service-area tools keep their own replace-by-name behaviour (`_replace_named_layer` in `logistics_tools.py`), which deletes the earlier result and says so when parameters changed. This plan does not change it; whether it should become "superseded" too is a separate owner question.
- Not seen in a real chat session. CI only: stand-in layers offline, real QGIS layers driving the real hook in the live job.

## Acceptance
Offline `tests/test_superseded_layers.py` (14) and live `tests/test_superseded_layers_live.py` (6) pass; ruff, mypy, ledger guard, master-list check pass. By hand: row D2 step 4 (buffer the same layer twice): the first buffer is renamed `... (superseded)`, the second holds the name, the reply says so.

## Guard tests
`tests/test_superseded_layers.py`, `tests/test_superseded_layers_live.py`; ledger entry `output-layers-mark-superseded`.

## Rollback
Set `cartogen_ai/mark_superseded` to `false`, or revert the commit. Layers already renamed stay renamed (they were kept, nothing was lost).

## Status log
- 2026-11-09: built from the owner's decision. Offline suite at the 54-error baseline with no failures; the live test has not run yet (first CI run).
