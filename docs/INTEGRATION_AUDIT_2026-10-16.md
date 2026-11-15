# Integration audit: do the new tools work with the old ones? (2026-10-16)

Question: after packages A to I and the gap-closing work (42 new tools, about 160 new allow-listed Processing algorithms), is routing correct,
are the new functions wired into the same mechanisms as the old ones, and does everything work together? This is a self-audit of the code; the
measurements below were run offline against the router and registry, the live behaviours are checked by `tests/test_integration_audit_live.py`
(first execution in CI). Nothing here is hand-tested.

## 1. Routing: measured, not assumed
Method: the router from before the roadmap (commit de89f63, 252 tools) was loaded next to the current one (294 tools) and fed every curated alias
phrase of the old tools (1565 phrases).

| Check | Result |
|---|---|
| Phrases whose own tool was offered before and is not now | **0 of 1565** |
| Average tools offered per request | 25.6 before, 26.5 now |
| Average schema text sent per request | 29 552 chars before, 28 709 now (**-2.9%**): the 42 new schemas average 569 chars against 1088 for the old ones |
| New tools offered as filler in unrelated old phrases | 2.5 per phrase on average (e.g. "empty layer" also offers the point-cloud and vector-tile tools) |
| Seven long compound requests mixing old and new capabilities (atlas + chart + export, DEM + elevation + profile, offline package, filter + label + undo, virtual layer + diagram, GRASS + clip, point cloud + 3D tiles + terrain) | every needed tool offered in all seven |

Reading: routing is correct and not more expensive. The filler is a side effect of description-word scoring over the 40-slot list and costs tokens
only in proportion to the (small) new schemas, so no scoring change was made: changing the shared scoring is exactly the kind of edit that broke
older releases (see the header of `tests/test_tool_router_basics.py`).

**One regression found and fixed.** "animate the layer over time" offered `export_temporal_animation_frames` before package B and stopped after it:
that tool had no aliases at all, and the new temporal tools took the word matches. Aliases added, golden row added.
**New permanent guard:** `TestEveryAliasStillOffersItsOwnTool` replays every curated alias phrase of every tool and requires its owner to be offered.

## 2. Integration points the new tools were missing from
| Mechanism | What the older tools had | Gap found | Fix |
|---|---|---|---|
| Undo (`undo_last_operation`, `_snapshot_registry.py`) | style, field-write and property tools can be reversed | the MODIFY tools added since package A had no snapshot, so undo could not reverse them | `set_layer_filter` (subset string), and `set_rule_based_labels`, `set_label_callout`, `set_layer_diagram`, `set_point_marker`, `set_raster_relief`, `apply_saved_symbol`, `set_layer_elevation`, `set_layer_temporal` (layer style round trip) registered; round trips are live tests. Not covered on purpose: edit-buffer tools (they have `undo_manual_edit`) and project-wide settings (snapping, terrain, time range). |
| Privacy gate and lineage (`egress_gate.argument_layer_names`) | `execute_read_only_sql` is scanned for layer names inside its SQL | `create_virtual_layer` names its layers only inside the SQL, so a virtual layer over a RESTRICTED layer was neither gated nor tagged with that source, and the derived layer looked open | SQL scan extended to `create_virtual_layer` (no "whole project" fallback: it can only read project layers); offline tests |
| Export advisory (`export_warning_for`) | export tools add a warning for RESTRICTED/SENSITIVE layers | `package_layers_offline`, `add_layout_chart`, `set_layout_atlas` put layer data into a file or layout without one | advisory note added (same rule, never blocks); live test |
| Prompt sensitive-rule cluster (`prompts.py`) | export and deliverable tools pull in the sensitivity rules | `export_layout`, `package_layers_offline`, `add_layout_chart`, `set_layout_atlas` were not in the list | added |
| Task library (`task_register.json`, 792 tasks; feeds the planner and the router's guaranteed tools) | tasks list the tools that do them | none of the 42 new tools was referenced by any task | linked the obvious ones: atlas tasks (3), chart tasks (3), elevation/DEM tasks (3), offline sync (1), 3D models (1). Task text was not rewritten. |
| Output styling (`output_style.py`) | slope, aspect, interpolation, heatmap, buffers, overlays, routes get a designed look | outputs of the 66 raster-family, GRASS and mesh algorithms opened as plain grey | continuous surfaces and distance/cost/density fields get the colour ramp; GRASS `v.buffer`, `v.hull`, `v.voronoi`, `v.delaunay`, `v.overlay`, `v.dissolve`, `v.net.iso`... get the roles of their native twins. Categorical and shaded results (r.clump, r.geomorphon, r.watershed, hillshade, viewshed, sieve, boolean rasters) are deliberately left alone: a ramp on class codes implies an order that is not there. |
| Operation classification (`tool_operations.py`) | every tool classified | already complete for all 42 (enforced by an existing test) | none |
| Router golden rows | 40 plain requests | all 42 new tools now have one | done earlier |

## 3. Looked at and left alone
* **Overlapping old and new tools** (`undo_last_operation` vs `undo_manual_edit`, `generate_chart` vs `add_layout_chart`, `elevation_profile` vs
  `add_layout_elevation_profile`, `apply_labels` vs `set_rule_based_labels`, `create_print_layout`'s inset vs `add_overview_map`): they do different
  things (one reverses a tool call, one an edit; one makes a picture file, one a layout item). The router keeps both offered for the ambiguous
  phrases (a script run over 28 phrases found the one regression above; the old-tool side of those cases is now permanent golden rows), so the
  model chooses from descriptions; no tool was merged or removed.
* **Pre-built chains (`chains.py`)**: no chain was added for the new tools. Chains are only worth shipping once their argument names are live-tested
  with a real layout and real data, and no new combination recurs often enough yet to justify one. This is the main remaining "nested workflow" gap.
* **Router scoring**: unchanged (see section 1).
* **GRASS and mesh on the GUI thread**: unchanged (the existing rule keeps Python-implemented algorithms off the worker thread after a CI crash).

## 4. What this audit cannot show
Whether a real model, with these 294 tools, picks the right one and passes the right arguments is not measured by anything here: the router tests
prove which tools are OFFERED, not which is CHOSEN. The live tests prove each mechanism on small synthetic layers in a Linux container, not a
desktop session, and the styling changes were checked as names and mappings, not by looking at rendered maps.
