---
description: Which code runs on QGIS's GUI thread, which on a worker, how long analyses stay responsive, and how Stop reaches a running tool.
---
QGIS objects (`QgsVectorLayer`, `QgsFeature`, `QgsProject`, widgets) may only be touched on the **GUI (main) thread**. An LLM turn, though, spends most of its time waiting on the network. Cartogen AI therefore splits the work:

| Thread | Runs |
|---|---|
| **GUI thread** | The dock, every ordinary tool, layer creation, project edits. |
| **`QgsTask` worker** | The whole agent turn (`CartogenAi.run`), model calls, and the network phase of fetch tools. Started by `core/services/task_runner.py`, so the UI stays live while the model thinks. |
| **Isolated process** | Model-written Python from `execute_pyqgis_script` (see [Security overview](@security/overview)). |

## How a tool reaches the GUI thread

The agent loop is on a worker, but most tools need QGIS objects. `ToolDispatcher` (`tool_dispatcher.py`) bridges them: it emits a signal with a `BlockingQueuedConnection`, the GUI thread runs the tool in a slot, and the worker waits for the result. The result container is passed as a plain Python `object` argument, not a `list`: PyQt converts `list` signal arguments to a `QVariantList` for queued delivery and the slot would then mutate a copy, so the caller always saw an empty result (a bug found live and fixed; the comment in the file says so).

## Two shortcuts, and why they are safe

Two sets in `agent_orchestrator.py` skip or split that bridge. The test `tests/test_processing_cost_guards.py` fails if any tool that makes network calls is in neither set, because a network call on the GUI thread freezes QGIS.

- **`NETWORK_ONLY_TOOLS`** (11): only HTTP or local file/CPU work, never `qgis.core` objects (`search_web`, `fetch_osm_features`, `search_hdx_datasets`, `search_stac_satellite_imagery`, `geocode_and_enrich`, `geocode_batch`, `generate_chart`, `aggregate_data`, the PDF and Word table extractors, `fetch_fts_funding_data`). They run directly on the worker.
- **`TWO_PHASE_TOOLS`** (15): the network part runs on the worker and the layer-building part on the GUI thread (`fetch_usgs_earthquakes`, `fetch_ucdp_conflict_events`, `find_incident_reports`, `fetch_gdacs_disaster_alerts`, `fetch_nasa_eonet_events`, `fetch_nasa_active_fires`, `fetch_geoboundaries`, `fetch_hdx_admin_boundaries`, `fetch_building_footprints`, `fetch_worldpop_population`, `ingest_osm_features`, `add_layer_from_path` and others). The pure parsers are separate functions, so they can be tested without QGIS.

## Keeping the GUI alive during long work

Three mechanisms, chosen by what the work touches.

### 1. Processing on a worker with a nested event loop

`tools/_background_processing.py`. `run_algorithm` runs an algorithm in a `QgsProcessingAlgRunnerTask` while the calling thread spins a nested Qt event loop, so the window repaints and Stop works, yet the call still returns the algorithm's result to the tool. It was built after a live measurement: routing graphs over a national road network took 292 to 572 seconds per call with QGIS "Not Responding" and no way to stop.

- **Only native C++ algorithms (`native:`) are run this way.** Python-implemented algorithms (`gdal:*`, `qgis:*`, `script:*`) stay on the GUI thread. They crashed the CI job when moved to a worker (PR #249); a later CI investigation could not reproduce the crash with path, layer-object or layer-id inputs, but nothing proves a worker is safe, so the safe default was kept (decision recorded 2026-10-12). A short pause on slope or hillshade is therefore expected.
- Algorithms that change your own layer (a selection) stay synchronous, because edits to a project layer are only safe on the GUI thread.
- If an algorithm ignores a cancel, its objects are kept alive and the call returns after a timeout, rather than destroying them under a running thread.
- `run_callable` runs pure Python (no QGIS objects) on a worker with the same Stop handling. Hub-siting ranking, allocation arithmetic, JIAF statistics and 2-opt route ordering use it.

### 2. Cooperative chunking for loops that touch QGIS objects

`tools/_chunked.py`. A loop over features, pairs or pixels cannot leave the GUI thread because it reads `QgsFeature` objects. Instead it works in slices of about **50 ms**: after each slice it lets Qt repaint, checks Stop, and every few seconds reports progress.

```python
for feat in features(layer, "Classifying facilities"):   # drop-in for layer.getFeatures()
    ...
```

About 90 loops across the analysis, validation, styling, export and import tools use this since rc36. Pressing Stop raises `AnalysisCancelledError`, which every tool lets through; a Stop inside an edit rolls the edit back. Off the GUI thread (a worker, the tests) nothing is pumped and the loop just runs.

### 3. Block-wise raster work

`unsupervised_classification` reads, classifies and writes the raster in row blocks of about 4 million values (centres are fitted on a sample, then every cell is assigned), so memory no longer grows with the raster. A raster over 400 million cells is refused with a "clip it first" message.

## Stop and progress

`core/agent/cancel_signal.py` holds module-level state for the duration of one request: a `should_stop` callable and a status callback. It is not passed through tool signatures because those are the model-facing schema. `run()` publishes the pair; long tools poll `cancel_signal.is_cancelled()` and report with `report("what I am doing")`. Everything in it is best-effort and never raises, so a broken callback cannot break a tool. The agent loop also checks Stop between rounds and between tool calls, and a project change counts as Stop (`project_session.py`).

## Scheduled workflows

`schedule_recurring_workflow` re-runs a saved step list on a `QTimer`. A single gate (`WorkflowScheduler._guarded_tick`) allows one heavy job at a time: a tick that would overlap another scheduled run or an active chat request is skipped (counted, not shown) and the next interval tries again. Interval floor 1 minute, at most 5 schedules, and only an allow-list of tools may be scheduled. See [Security overview](@security/overview).

## Chat window growth

`ChatViewPresenter.trim_scrollback` removes the oldest whole items once the chat holds more than 300, keeping the newest 200, and shifts the positions of cards that are edited in place. The saved conversation is untouched. The 300 and 200 figures are estimates, not measured.

## What has and has not been verified

The slicing, the blocked classification and the scheduler gate have offline tests and live QGIS tests in CI. The speed-up and Stop latency on large real data have **not been measured**, and Stop against a long-running job has not been proven in a hand test. See [Status and open work](@project/status).
