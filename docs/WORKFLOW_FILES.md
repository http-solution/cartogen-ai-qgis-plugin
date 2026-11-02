# Sharing a workflow as a file

A **workflow file** is a small text file that records the steps of an analysis so a colleague can read it, point it at their own layers and run it. Colleagues swap them by e-mail, a shared drive or GitHub. A workflow file is **data, not a program**: it lists tool calls, nothing else, and the plugin only ever runs calls from a short reviewed list, through the same checks and confirmations as a request you type yourself.

> **Status (2026-11-02).** Built and merged; the automated tests, including the ones that run in real QGIS in CI, pass. **No person has yet tried it end to end**: how the export card and the import dialog look and read, a file moving between two machines, and the "confirm, then carry on" path are all untried. The checks under each heading say what is known. Tell us what reads badly.

## Make one

1. Run your analysis as usual. The plugin records, for every layer it makes, which tool made it, with which settings, from which layers.
2. Ask: *"export this workflow as a file"* (name the final layer if there are several).
3. A card shows the **whole file** before anything is written, with where it will be saved (by default the project's `exports/workflows` folder) and which recorded steps were left out and why. Press **Confirm** to write it. Nothing is written before that.

What goes in: the steps in order, the settings of each step, a **role** for every layer the analysis started from (see below), the data sources behind fetched layers (name, address, licence from the plugin's own table, which is not checked against the provider), and two limitations the plugin adds itself.

What never goes in: layer contents, file paths, credentials, your e-mail address. Layer **names** are replaced by roles where they were inputs; a layer name that appears inside a longer text (for example inside a filter expression) is left as it is and the card warns you. Read the card; it is the file.

A step is left out, with the reason, when its tool is not on the shareable list (the list is below) or one of its settings looks like a file path or web address. If a left-out step made a layer that a later step needs, that layer becomes a role too, so the colleague supplies it.

## Open one

1. **Plugins > Cartogen AI > Open workflow file...** and choose the file. (Only you can do this from the menu. No chat request and no tool can open or run a workflow file, so a document or web page the assistant reads cannot load one.)
2. If the file breaks a rule it is shown with the reasons and there is no Run button. The reasons are plain sentences that name the step ("Step 3 (set_layer_sensitivity): `set_layer_sensitivity` is not on the list of tools a shared workflow may use.").
3. Otherwise the dialog shows, top to bottom: a reminder that **someone else wrote it**; its name; the **checksum** (SHA-256: if the author tells you theirs, check it matches); the author's own text; **every step** with its kind of change (READ, CREATE, MODIFY) and its settings; one **layer chooser per role**; **Start at step**; any problems and checks; the author's limitations and data sources.
4. Choose a layer for each role. Only layers of the right kind (vector or raster) are offered. A wrong kind is a problem and blocks Run. A different geometry type (for example points where the author used polygons), or a missing field the role expects, is shown as a **Check** only: you may know better.
5. Press **Run**. Run stays disabled until every role in use is chosen and no problem remains.

## What happens when it runs

The plugin runs the steps one at a time, itself, **without asking an AI model** and without sending the file's text anywhere. Each step goes through the same path as a chat request: write confirmations, the protected-layer (egress) check, sensitivity tags, the result checks, undo snapshots and a check that the layers exist, so a layer that is missing is refused before step 1.

The run **stops** at the first error, the first step that needs your **Confirm** (the usual card appears), when you press **Stop**, or when the safety guard trips: the same call (same tool, same settings) made a third time in one run, or a tool failing three times in a row, or eight failures in all. The chat says which steps ran and which did not.

After a Confirm card: confirming runs **that one step only**. To carry on, open the file again and set **Start at step** to the next number. A step that refers to the result of an earlier step (written `$2.layer_name`) cannot start after that step, because its result is no longer there; the dialog says so.

Layers made by a run remember the workflow's name and checksum, and reports show "[from workflow file 'NAME' sha256 ...]" beside those steps.

## What a file can and cannot do

- At most **20 steps** and **256 KB**.
- Only these tools (the same reviewed list the plugin's local MCP server draws from, plus the fixed-service fetch tools):
  - **Read:** `check_pcode_hierarchy`, `check_pcode_uniqueness`, `field_statistics`, `find_broken_layers`, `find_tools`, `get_attributes`, `get_crs`, `get_dataset_status`, `get_feature_count`, `get_layer_confidence`, `get_layer_extent`, `get_layer_metadata`, `get_layer_sensitivity`, `get_layers`, `get_provenance_record`, `list_bookmarks`, `list_layout_items`, `list_layouts`, `list_map_themes`, `list_relations`, `list_schema_contracts`, `measure_distance`, `validate_schema`, `verify_crs_compatibility`.
  - **Make a new layer or change presentation:** `apply_categorized_style`, `apply_graduated_style`, `apply_labels`, `buffer_analysis`, `calculate_service_area`, `centroid`, `change_layer_color`, `clip_layer`, `convert_to_singlepart`, `convex_hull`, `delaunay_triangulation`, `difference_layers`, `dissolve_layer`, `find_nearest_features`, `fix_geometries`, `intersect_layers`, `join_by_attribute`, `merge_layers`, `rename_layer`, `reproject_layer`, `set_layer_transparency`, `simplify_geometry`, `spatial_join`, `toggle_visibility`, `union_layers`, `voronoi_polygons`.
  - **Fetch from a named service (no web address in the file):** `fetch_building_footprints`, `fetch_fts_funding_data`, `fetch_gdacs_disaster_alerts`, `fetch_geoboundaries`, `fetch_hdx_admin_boundaries`, `fetch_nasa_active_fires`, `fetch_nasa_eonet_events`, `fetch_osm_features`, `fetch_ucdp_conflict_events`, `fetch_usgs_earthquakes`, `fetch_worldpop_population`, `ingest_osm_features`.
- Not allowed, ever: scripts, deleting or replacing project state, tools that take a free file path or web address, exports, memory or sensitivity changes, tools that have their own confirm step, and `confirmed` anywhere in a file (a file cannot approve anything).
- A setting that looks like a file path or web address is refused (`/`, `\`, `~`, a drive letter, `file:`, `://`, `..`). Text settings are at most 500 characters.
- Layers tagged RESTRICTED or SENSITIVE keep their protection: using one in a step is checked by the usual egress gate.

## Trust and limits

- A workflow file was written by someone else. The dialog lists every call before anything runs; read it. The list is reviewed and the settings are checked, but no check can prove a tool is harmless for every setting.
- Running the same steps on different data gives different numbers. The exported file says it has **not been run again** from the file.
- The licence and source lines are the author's record plus the plugin's own table; they are not checked against the provider. Check them before you publish a map made from fetched data.
- The history records the settings the assistant sent to each tool. If a tool later corrected a setting, the file carries the original.

## Sharing

Send the file as it is. If you put examples on GitHub, `docs/examples/workflows/` holds one worked example (`access-to-care.cgworkflow.json`, written by hand and not exported or run); a pull request adding another is welcome if it validates (`python -m unittest tests.test_workflow_file`).

## File format (version 1)

```json
{
 "format": "cartogen-workflow", "version": 1,
 "name": "...", "description": "...", "author": "optional", "created_with": "optional",
 "roles": {"facilities": {"kind": "vector", "geometry": "point", "fields": ["name"], "about": "health facility points"}},
 "steps": [
  {"tool": "buffer_analysis", "arguments": {"layer_name": "@facilities", "distance": 5000, "output_name": "reach"}, "note": "optional"},
  {"tool": "get_feature_count", "arguments": {"layer_name": "$prev.layer_name"}}
 ],
 "limitations": ["..."],
 "data_sources": [{"name": "...", "url": "https://...", "licence": "..."}]
}
```

`@role` stands for one of your layers, chosen when you open the file. `$2.field` and `$prev.field` mean a field of an earlier step's result. A step's `args` (the older preset spelling) is accepted and converted. A newer `version` than the plugin reads is refused with a message to update.

Plans and decisions behind this: `docs/plans/PLAN-047-roadmap-g-owner-decisions.md`, `docs/plans/PLAN-048-shareable-workflow-file.md`.
