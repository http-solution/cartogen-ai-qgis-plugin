---
description: What the plugin remembers, where it is stored, and how results survive Save and Reopen.
---
Cartogen AI keeps several kinds of state. Each has a different owner, lifetime and risk.

| State | Stored in | Lifetime | Module |
|---|---|---|---|
| **Conversation** | A `QgsProject` entry `cartogen_ai/chat_transcript` inside the `.qgz` | Life of the project; bounded at 2,000 messages / 2,000,000 characters, oldest dropped first | `chat_persistence.py` |
| **Spatial memory** | A sidecar SQLite database next to the project (project notes), plus global user memory in `QgsSettings` (learned preferences) | Until you clear it | `memory.py` |
| **Analysis results** | `<project folder>/data/20_processed/cartogen_results.gpkg` | Until deleted; survives Save and Reopen | `results_store.py` |
| **Design state** | Per-project record of what was drawn and how | Project | `map_state_memory.py` |
| **Layer lineage** | Layer metadata and custom properties inside the project | Project | `lineage.py` |
| **Provenance** | A deterministic record per layer, optionally a sidecar file | Project | `provenance.py` |
| **Your profile** | `user_profile.md` in your QGIS profile folder | Until you edit or delete it | `onboarding_profile.py` |
| **Evidence, API trace** | Local folders you switch on (off by default) | Until you delete them | `evidence.py`, `api_trace.py` |
| **In-flight turn** | Process memory | One request | `history_manager.py`, `usage_tracker.py`, `cancel_signal.py` |

## Conversation

The full transcript is saved in the project file **by default** (since rc8; an owner decision, because a mapping project has a purpose and a lifetime and the conversation is part of its context). A project file is a shareable artefact, so a conversation about sensitive material travels with it. Turn it off in Settings (*Save the conversation in the project file*) and use **Clear Saved Chat** in the Memory window to delete what is saved; copies you already shared keep theirs. `chat_persistence` must only be called on the main Qt thread because `QgsProject` is not thread-safe.

Within a turn, `history_manager.py` stores messages under a lock, trims, and compacts old tool results mid-turn so a long turn does not resend large results every round; a digest message marks dropped content. Cross-turn history stores only the user message and the assistant's final prose, never raw tool results.

## Results that survive Save and Reopen

Analysis tools produce QGIS **memory layers**. QGIS saves a memory layer's definition in the project but not its features, so a service area that took 44 minutes came back empty after reopening (rc7 smoke test F06). The results store writes the layer into a per-project GeoPackage and points the layer at it, keeping its id, tree node and renderer. Details worth knowing:

- Each persist writes a **new** table (name plus timestamp) and re-points the layer, because overwriting a table a layer has open can lock the file on Windows; older tables are dropped afterwards, best effort.
- Provenance goes into the layer's `QgsLayerMetadata` abstract.
- An **unsaved project has no folder**: nothing is written, the caller is told, and the chat asks you to save first. No file appears in a surprise location.
- A result that replaces a layer of the same name never overwrites one you made yourself: plugin results are marked as the plugin's own; a same-named layer of yours is renamed and the reply says so (rc22).
- `save_project` lists temporary layers that will come back empty.

## Lineage and provenance

When a tool creates or changes a layer it is tagged with the tool, its parameters, its source layers (by name and id) and the time. The data-egress gate follows lineage through renames and duplicates, so a layer derived from a protected one keeps its protection; a name shared by several layers takes the strictest level (#150). `get_provenance_record` and `write_provenance_sidecar` expose the record.

## Staleness: one turn, one project

`project_session.py` gives each running turn the identity of the project open when it started. A project clear or read bumps a generation counter, which stops the turn at its next checkpoint (it is also polled by long tools) and makes the tool path and history append refuse to touch whatever project is open by then (#147). A stale turn cannot deliver a result or act on another project.

## Export and delete

`data_export.py` produces a consolidated, portable export of what the plugin holds about you (memory, profile, saved chat with a digest and the retention note). It is deliberately Qt-free pure Python/JSON. The Memory dialog also deletes memory and the saved chat. See [What leaves your machine](@security/privacy).
