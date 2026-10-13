---
description: How tools are registered, classified, routed to the model and chained, with the categories and counts.
---
A **tool** is a Python function the model may call by name with JSON arguments. There are **{{tools}}** of them. Their arguments are documented in the generated [Tool reference](@tools/index).

## Registration

Each tool module in `core/agent/tools/` decorates its functions:

```python
@register_tool("buffer_analysis", "Buffer a layer by a distance in metres ...", {"type": "object", "properties": {...}, "required": [...]})
def buffer_analysis(layer_name, distance, ...):
    ...
```

`register_tool` stores the function in `TOOL_REGISTRY` and its schema in `TOOLS_SCHEMA`. The decorator must sit **directly** on the function the model will call: in rc24 a helper was inserted between them, the registry held the helper, and every model call to `run_allowlisted_processing_algorithm` failed until rc38. A test now checks that every registered function accepts the arguments its schema advertises (`tests/test_tool_registry_signatures.py`).

Underscore-prefixed modules are shared helpers, not tools: `_background_processing`, `_chunked`, `_edit_session`, `_layer_checks`, `_network_closure`, `_paths`, `_processing_allowlist`, `_qgis_enum_compat`, `_snapshot_registry`, `_urllib_retry`, `_cache_utils`.

## Operation types

`tool_operations.py` classifies every tool as one of **READ**, **CREATE**, **MODIFY**, **DELETE** or **PUBLISH**. The taxonomy drives:

- the **plan gate** (opt-in): only DELETE and PUBLISH calls need a validated plan;
- the **loop guard**: a round only counts as progress if a state-changing call succeeded (CREATE, MODIFY, DELETE, PUBLISH);
- the **transaction log** and best-effort undo;
- a coverage test, so a new tool cannot be added without a type.

## Choosing which tools the model sees

Offering all {{tools}} schemas every round would cost tokens and confuse the model, so each turn offers about **40**.

1. `capabilities.py` maps phrases in the request to **capabilities** (OpenStreetMap data, HDX boundaries, buffer, clip, reproject, slope, contours…), each listing the dedicated tools in best-first order. A capability with no dedicated tool names the constrained Processing tool and the script fallback instead. A test checks that every tool named in the table exists in the registry.
2. `services/tool_router.py` ranks the rest by keyword and alias match and carries over tools used in the previous two turns.
3. The model can call **`find_tools`** when a step needs something outside the offered list; the router then offers it.

## Chaining

- **`run_steps`** sends up to 8 dependent calls in one round trip. References are whole-string only (`$2.layer_name`, `$prev.x`). The plugin validates the chain against the open project before running anything (layers exist and have the right kind and geometry, no buffering a geographic-CRS layer, numeric style fields), runs the steps one at a time through the normal path, and stops at the first error or pending confirmation. No nested `run_steps`, no deleting tools.
- **Chains** (`chains.py`) are eleven vetted recipes offered when a request names all their steps: exclusion-zone split, buffer then clip, coverage gap, outside distance, terrain contours, terrain slope, clip DEM then slope, clip-style-zoom, reproject then export, population exposure, admin boundary validation. `discovery.py` inspects the project so their slots bind to real layers and suggest a UTM zone.

## What a tool returns

`tool_result.py` is the one place that says what a result is. Most tools return a dict; read tools may return a list. Only a dict with an `error` key is a failure, and a `None` becomes the standard "Execution failed unexpectedly." Results can carry a `status` such as `PREVIEW_REQUIRED` (nothing ran yet) that the loop treats specially.

## Destructive tools

`remove_layer`, `load_project`, `field_calculator`, `calculate_area` and `calculate_length` need a `confirmed` flag. The dispatcher strips `confirmed` from any model-supplied arguments, so the only path to `confirmed=True` is a click on the confirmation card in the dock. Four analysis tools that rewrite their own output field are deliberately left ungated (decided 2026-08-22: idempotent, lower harm). Exports over a non-empty file the plugin did not write ask first.

## Tool tiers for model-written code

1. **Dedicated tools**: the normal path.
2. **`run_allowlisted_processing_algorithm`**: a fixed list of Processing algorithms that already appear in the codebase. Unknown algorithm ids and unknown parameter names are rejected before anything runs; output is always in-memory; no `FORMULA` or `EXTRA` raw-argument parameters.
3. **`execute_pyqgis_script`**: a last resort, in an isolated process. See [Security overview](@security/overview).

## Where each domain lives

| Domain | Modules |
|---|---|
| Vector and geoprocessing | `vector_tools` (the largest), `analysis_tools`, `sampling_tools` |
| Raster and terrain | `raster_tools`, `raster_numpy`, `dem_tools`, `multimodal_remote_sensing`, `imagery_extraction` |
| Styling, layouts, export | `styling_tools`, `humanitarian_look_tools`, `layout_tools`, `export_tools`, `reporting_tools`, `cartographic_advisory_tools` |
| Humanitarian data | `humanitarian_tools`, `event_data_tools`, `incident_search_tools`, `hazard_monitoring_tools`, `table_importers` |
| Logistics | `logistics_tools`, `impedance_tools`, `barrier_tools`, `corridor_tools`, `critical_link_tools`, `allocation_tools` |
| Severity and JIAF | `jiaf_engine`, `jiaf_inputs`, `jiaf_patterns`, `jiaf_review`, `mcda_tools`, `survey_tools`, `trigger_tools`, `task_grid_tools` |
| Governance and QA | `schema_contract_tools`, `pcode_validation_tools`, `dataset_status_tools`, `provenance_tools`, `sensitivity_tools`, `confidence_tools`, `qa_checklist_tools`, `transaction_tools` |
| System | `system_tools` (web search, scripts), `project_tools`, `project_tidy_tools`, `task_tools`, `tool_discovery`, `monitoring_tools`, `db_and_workflow_tools`, `data_export_tools`, `engineering_tools` |

The module names come from the tool registry; the [Tool reference](@tools/index) lists every tool with its category.
