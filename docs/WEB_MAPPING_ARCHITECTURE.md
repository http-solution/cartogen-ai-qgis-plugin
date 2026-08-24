# Cartogen AI Web Mapping Architecture — Ground-up Implementation Notes

## Source evidence inspected

### Existing Cartogen QGIS implementation

- `src/cartogen_ai/core/ui/chat_tab_widget.py`
  - real chat transcript and project-bound history;
  - file attachments;
  - quick suggestions;
  - prompt refinement with explicit user choice;
  - status and usage indicators;
  - stop/cancel control;
  - task-step reporting.
- `src/cartogen_ai/core/ui/tasks_tab_widget.py`
  - plan progress and task states;
  - preview/confirm/apply safety;
  - task inspector with generated code/rationale;
  - retry/edit workflow;
  - plan history and spatial memory.
- `src/cartogen_ai/core/agent/agent.py`
  - provider abstraction;
  - map-context injection;
  - tool registry and routing;
  - task manager and lineage binding;
  - main-thread tool dispatch boundary.
- `src/cartogen_ai/core/agent/task_runner.py`
  - background LLM execution;
  - cancellation;
  - status callbacks;
  - completion/error callbacks.
- `src/cartogen_ai/core/agent/tools/humanitarian_tools.py`
  - real HDX discovery;
  - OSM Overpass fetch;
  - geoBoundaries fetch/import;
  - provenance-oriented results.
- `src/cartogen_ai/core/agent/tools/monitoring_tools.py`
  - saved read-only workflows;
  - recurring monitoring semantics;
  - diff against previous runs;
  - explicit restriction against unattended destructive tools.
- `src/cartogen_ai/core/agent/tool_router.py`
  - relevance filtering and aliases before provider calls.

### QGIS reference implementation inspected

- `QgsMapCanvas`
  - a real map canvas owns layers, CRS, rendering, extent, selection, overlays, and map tools;
  - the web equivalent must be a first-class map state, not a decorative `<div>`.
- `QgsLayerTree`
  - layer order and visibility are explicit model state;
  - the web layer panel must be backed by a real layer tree model.
- `QgsTask` / `QgsTaskManager`
  - queued/running/complete/terminated states;
  - cancellation and progress are first-class;
  - web jobs must expose the same state machine.
- `QgsProcessingAlgorithm`
  - algorithms have stable IDs, display names, descriptions, parameters, outputs, and feedback;
  - web analysis operations need the same typed operation contract instead of ad-hoc buttons.

## Web product architecture

### Three surfaces

```text
Chat / agent transcript | Map canvas / layer tree | Inspector / tools / jobs
```

The chat is the primary input. The map is the primary spatial output. The right panel is context and control, not a catalogue of unrelated buttons.

### Core backend objects

- `projects`: project identity, CRS, extent, organization;
- `project_layers`: layer metadata, visibility/order, source/provenance, style;
- `project_features`: PostGIS geometry and properties;
- `documents`: source/context documents and hashes;
- `agent_runs`: prompt, model/provider, context snapshot, response, status;
- `agent_steps`: ordered tool/analysis steps, parameters, rationale, preview, confirmation, status;
- `analysis_jobs`: queued/running/completed/failed/cancelled execution;
- `workflow_schedules`: saved read-only workflow, interval, next run, last run, run history;
- `lineage_events`: source layers, operation, parameters, user, timestamps, output layers.

### AI contract

The model never writes directly to the database or map. It returns a typed plan:

```json
{
  "objective": "...",
  "data_requests": [],
  "steps": [
    {
      "id": "step-1",
      "tool": "search_hdx_datasets",
      "arguments": {},
      "rationale": "...",
      "requires_confirmation": false
    }
  ],
  "warnings": [],
  "expected_outputs": []
}
```

Execution is server-side, typed, auditable, cancellable, and read back before the assistant reports success.

### Dataset discovery contract

Chat may discover candidate datasets from HDX, OSM, geoBoundaries, STAC, or configured catalogues. Discovery returns candidates only. Import requires explicit user approval unless the source is configured as an approved read-only connection.

Every imported dataset retains:

- source URL;
- provider/dataset ID;
- resource date;
- retrieval timestamp;
- licence;
- CRS/geographic level;
- schema summary;
- limitations;
- raw source reference.

### Editing contract

Feature edits require:

```text
select feature
→ inspect current properties/geometry
→ propose edit
→ show before/after diff
→ user confirms
→ transaction applies
→ lineage event recorded
→ map/table refresh
```

No direct browser-only edits are authoritative.

### Scheduling contract

Schedules are persisted backend objects. Only approved read-only workflows may run unattended initially. Each run creates a job and run record with:

- schedule ID;
- workflow version;
- input layer/document versions;
- start/end time;
- status;
- output/diff summary;
- error details.

## Implementation order

1. Real Leaflet map and layer-tree model — current foundation.
2. Chat transcript with typed agent-run/step records.
3. Dataset discovery candidates and explicit import approval.
4. Typed analysis registry replacing operation-specific UI branching.
5. Map selection, inspector, before/after edit diff, transaction API.
6. Background job progress/cancel/retry.
7. Read-only schedule persistence and run history.
8. Strict Directus organization permissions.
9. Browser acceptance suite for the full journey.

## Current truth

The current web app has a working Gemini planner, PostGIS layers, Leaflet basemap, uploads, and analysis jobs. It does not yet have the complete professional web mapping product described above. Dataset discovery/import, typed agent step persistence, editing/diffs, and persisted scheduling are the next real implementation gates.
