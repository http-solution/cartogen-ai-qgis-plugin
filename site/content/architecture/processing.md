---
description: The Cartogen AI Processing provider: two native algorithms usable in the Toolbox, the Model Designer and qgis_process.
---
The plugin registers a **QGIS Processing provider** (`id` `cartogen`, shown as *Cartogen AI*) so analyses can be used without the chat: in the Processing Toolbox, the Graphical Model Designer, batch processing and the headless `qgis_process` CLI.

| Algorithm | id | Group | What it does |
|---|---|---|---|
| **Optimal Hub Siting (Demand Coverage)** | `cartogen:optimalhubsiting` | Logistics & Network | Ranks candidate hub points by average straight-line distance to demand points. |
| **Service Area from Network** | `cartogen:calculateservicearea` | Logistics & Network | Multi-band service areas from a road network layer. |

Both live in `src/cartogen_ai/processing/provider.py`. The manifest declares `hasProcessingProvider=yes`, `plugin_main.py` calls `initProcessing()` from `initGui()` to add the provider to `QgsApplication.processingRegistry()`, and `unload()` removes it, so load, unload and reload work without restarting QGIS (a CI smoke test checks this).

## Two directions of reuse

- **Plugin → Processing:** the two algorithms above expose the plugin's own analyses.
- **Processing → plugin:** the agent can run a fixed list of existing Processing algorithms through `run_allowlisted_processing_algorithm`. Native algorithms that create new data run on a worker with Stop; Python-implemented ones stay on the main thread. See [Threads, tasks and Stop](@architecture/threading).

Only these two algorithms are registered. The other {{tools}} tools are available through the chat, not the Toolbox.
