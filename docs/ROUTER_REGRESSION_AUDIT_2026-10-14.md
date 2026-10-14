# Router regression audit, 2026-10-14

**Trigger.** Owner report: "create layer for Jordan ADM1" worked in an earlier version and not now; "every release breaks previous work".

**Method.** Forty plain requests (layers, boundaries, export, buffer, service area, layout, dashboard, hazards ...) were replayed through the tool router of all 43 release commits from rc12 to 1.16.2 (git worktrees; `tools/replay_router_across_releases.py`), and the tools offered were diffed release to release. This is deterministic; it does not need a model.

**Finding.** Up to rc21 a short request such as "create layer for Jordan ADM1", "zoom to the layer X", "remove the layer X" or "export X to CSV" was offered `add_layer_from_path`, `zoom_to_layer`, `get_layer_extent`, `remove_layer`, `export_layer`, `reproject_layer`, `clip_layer` and the other layer tools. From rc23 (the cost work, commit a127885, "quieter tool ranking") they were not: the generic words "layer", "add", "create", "export", "get", "set" ... were removed from tool-name matching for **every** request, although the measurement that justified it was made on long requests. With nothing left to score, ties were broken alphabetically, so the model was offered `apply_*` and `calculate_*` tools instead. Nothing crashed and no test failed: the model simply never saw the tool, so it answered "no fetcher is active" or improvised.

**Not the cause.** System-prompt rules (39 rules before and after), the number of tools offered (about 31 on average before and after), the model, the downloads.

**Fix.** The generic-word discount and the cap on description matches now apply only to long requests (more than 25 words), as the original comment said. A permanent guard, `tests/test_tool_router_basics.py`, lists 28 plain requests with the tools they must be offered; it fails on the old router (checked) and passes now. Routing phrases for ADM0 to ADM5, "governorate" and "admin boundaries" were added at the same time.

**Not covered by this audit.** Behaviour that depends on the model's choices (what it does with the tools it is offered), prompts longer than 25 words, and anything in the QGIS UI. Those still need the hand-test rows. The replay tool and the golden table are the first line of defence for routing only.
