# PLAN-048: A shareable workflow file (owner decisions 1 and 4 of PLAN-047)

Status: in progress

## Goal
A person can export what they did as a workflow file, send it to a colleague (GitHub, email, a shared drive), and the colleague can inspect every step, map the file's layer roles to their own layers, and run it, with every step going through the same confirmation, egress and sensitivity gates as a chat request. The file is data only: it contains no code and cannot make the plugin do anything outside a short, reviewed list of tools. This is the whole of the "workflow builder" and "marketplace" the owner chose (PLAN-047: share as files, no node editor, no store).

## What exists today (read 2026-11-02)
- **Presets** (`save_workflow_preset` / `load_workflow_preset`, `db_and_workflow_tools.py`): a JSON string kept in QgsSettings, shape `{"steps": [{"tool", "args"}]}`. Nothing is validated when it is saved. `run_monitoring_workflow` runs only seven read-only analysis tools, and it calls each tool function directly (`func(**args)`), not through the agent's `_execute_tool`, so it does not pass the egress gate, the write confirmations or the result gate. That is acceptable for seven read-only tools and is **not** a model for this plan: the shared-file runner must not call tool functions directly.
- **`run_steps`** (`step_runner.py`): `{"steps": [{"tool", "arguments"}]}`, whole-string references `$2.layer_name` / `$prev.x`, at most 8 steps, no nested `run_steps`, no deleting tools, validated before anything runs, each step run through the normal tool path. The file format should reuse its step shape and reference syntax, not invent a third one.
- **Recorded lineage** (`lineage.py`, used by `workflow_report.steps`): every layer a tool made carries tool, parameters, input layers and time. That is the raw material for "export what I did".
- **The MCP lists** (`mcp_policy.ALLOWED_TOOLS`, `WRITE_TOOLS`): the plugin's first reviewed lists of tools that are safe to hand to something outside the chat.

## Scope
In:
1. **The format** (version 1), below.
2. **A pure validator** (`core/agent/workflow_file.py`, no QGIS; placed in `core/agent`, not `core/services`, because it uses the agent's tool lists and `step_runner`): parse, check, normalise, report problems as plain sentences. Everything the import will rely on is decided here and unit-tested offline.
3. **Export**: a model-callable tool `export_workflow_file(layer_names, path?)` (classified PUBLISH; the existing overwrite card applies) that builds a file from recorded lineage, replacing layer names with roles, and shows what it wrote.
4. **Import**: a menu action in the plugin ("Workflows > Open workflow file..."), person-initiated only. A dialog lists every step (tool, kind of change, arguments with roles shown), the file's SHA-256, its limitations and its data sources, asks the person to map each role to a project layer, then runs the steps one at a time through the normal tool path with a Stop button.
5. A worked example file for the service-coverage analysis and a short guide page.

Out: a node editor (decided against); any code in a file; running a file from the model's own initiative (see Safety); a catalogue, signing or install-from-URL (decided against); scheduling a shared file (the monitoring presets stay as they are); changing `run_monitoring_workflow`.

## The format (version 1)
A UTF-8 JSON file, extension `.cgworkflow.json`, at most 256 KB.
```
{
  "format": "cartogen-workflow", "version": 1,
  "name": "Access to care by district", "description": "...",
  "author": "optional free text", "created_with": "1.18.6",
  "roles": {"districts": {"kind": "vector", "geometry": "polygon", "fields": ["admin_name"], "about": "admin units to score"},
            "clinics":   {"kind": "vector", "geometry": "point"}},
  "steps": [ {"tool": "buffer_analysis", "arguments": {"layer_name": "@clinics", "distance": 5000, "output_name": "clinic_reach"}, "note": "5 km around each clinic"},
             {"tool": "spatial_join", "arguments": {"target_layer": "@districts", "join_layer": "$prev.layer_name"}} ],
  "limitations": ["Distances are straight-line, not travel time."],
  "data_sources": [{"name": "OCHA COD-AB", "url": "https://...", "licence": "CC BY-IGO"}]
}
```
- `@role` (whole string) stands for a project layer the person picks at import; `$n.field` / `$prev.field` are `run_steps`' own references to an earlier step's result. A role must be declared in `roles`.
- `arguments` is the key (as in `run_steps`); a preset's `args` is accepted on import and converted, with a note.
- A file never carries data, credentials, a person's file paths or e-mail addresses.

## Safety rules (each one has a test)
1. **Tool list.** A step's tool must be on one reviewed list. Proposed: `mcp_policy.ALLOWED_TOOLS` plus `WRITE_TOOLS` plus the fixed-service fetch tools in `source_record.SOURCES`; the lists move into one shared module so MCP and files cannot drift apart. Never: `execute_pyqgis_script`, anything classified DELETE, `run_steps` / `create_plan` and the other tools `step_runner.NOT_BATCHABLE` names, tools that take a free file path or URL (`add_layer_from_path`, `add_web_layer`, exports), tools that store memory or change sensitivity, tools with a `confirmed` parameter (their own confirmation stays in chat).
2. **Arguments.** Only keys the tool's schema advertises; `confirmed` anywhere is a refusal, not a silent drop (a file that tries it is suspicious and the person is told); required keys present; value types match the schema; strings at most 500 characters; any key or value that looks like a path (`/`, `\`, `~`, a drive letter, `file:`) is refused in version 1.
3. **References.** Every `$` reference points at an earlier step; every `@role` is declared; at most 20 steps (run_steps' cap of 8 applies per batch, so a longer file runs as consecutive batches).
4. **Show everything first.** Nothing runs until the person has seen every step with its arguments and has mapped every role. The dialog says plainly that the file was made by someone else.
5. **Same gates.** Each step runs through the agent's normal tool path (`_execute_tool`), so write confirmations, the egress gate, sensitivity, the result gate and the source record all apply. A step that returns PREVIEW_REQUIRED or EGRESS_BLOCKED stops the run and says so, as `run_steps` does.
6. **Person-initiated only.** There is no tool that opens, imports or runs a file. A document the model reads cannot make the plugin load a workflow. Export is a tool because writing a file the person asked for is an ordinary PUBLISH call.
7. **Provenance.** Layers made by an imported run carry the workflow's name and SHA-256 in lineage, so a workflow report can say which file produced them.
8. **Export privacy.** Export previews the file before writing. It replaces layer names with roles, flags and removes absolute paths, never writes layer contents, and leaves the author blank unless the person types one.

## Acceptance
1. **Offline (pure):** the validator accepts the worked example and refuses each of: wrong format or version, oversize, malformed JSON, an unlisted tool, a DELETE tool, a path-like value, `confirmed`, an undeclared role, a forward reference, an unknown argument key, a wrong-typed value, more than 20 steps. Every refusal names the step and the reason.
2. **Offline:** a round trip: lineage of a two-step chain exports to a file that validates, with layer names replaced by roles and no path in it.
3. **CI live:** export from a real two-layer chain; import with a role mapping; the steps run through the normal path; a protected layer mapped to a role is refused by the egress gate; a step that needs confirmation stops the run.
4. **Hand test (owner):** export a service-coverage run, open the file on another machine or profile, read the dialog, map the roles, run it, and compare the result with the original.
5. Not claimed: that the colleague's result equals the original (it depends on their data); that every tool on the list is safe with every argument (the list is reviewed, the arguments are validated, the gates run, and the person has seen the call).

## Guard tests
To be written with the work: `tests/test_workflow_file.py` (validator and round trip, offline), `tests/test_workflow_file_live.py` (export, import and gates, CI only), a test that the MCP lists and the file list come from one module and that every listed tool exists and is classified as claimed, and a test that no tool function with "import" or "run" and "workflow file" in its purpose is registered (acceptance of rule 6).

## Rollback
The menu action and the export tool are the only entry points: remove them and nothing else changes. The format carries a version; a later version is refused by an older plugin with a plain message.

## Staging
1. Validator, format schema, shared tool list, offline tests (no UI). 2. Export tool and the round-trip test. 3. Import dialog and runner (needs a UI look that cannot be checked in this sandbox: CI live test plus the owner's hand test). 4. Worked example and guide page. Each stage is its own pull request and its own status-log line.

## Decisions needed from the owner (recommendations first)
1. **File extension and name:** `.cgworkflow.json` (recommended; opens in any editor, and the name says what it is) or plain `.json`.
2. **Fetch tools as steps:** allow the twelve fixed-service fetch tools (recommended: a shared workflow often starts with "fetch the boundaries") or start with analysis and styling only.
3. **Step cap:** 20 per file (recommended) or 8 to match `run_steps`.
4. **Where shared examples live:** a `docs/examples/workflows/` folder in this repository (recommended; reviewed by pull request) or none until people ask.

## Status log
- 2026-11-02: plan written from the owner's PLAN-047 decisions 1 and 4. No code. Findings recorded above: the existing preset runner calls tool functions directly and so skips the gates (fine for its seven read-only tools, not to be copied); `run_steps` already defines the step shape and references to reuse.
- 2026-11-02: the owner said "go with the recommendations": the four decisions are taken as recommended. (1) Extension `.cgworkflow.json`. (2) The twelve fixed-service fetch tools are allowed as steps in a file (not over MCP). (3) Step cap 20 per file. (4) Worked examples live in `docs/examples/workflows/`.
- 2026-11-02: stage 1 built (offline only, no entry point, nothing a user can reach yet). `core/agent/tool_lists.py` is now the one place the reviewed lists live (`READ_TOOLS`, `WRITE_TOOLS`, `FETCH_TOOLS`, `FILE_TOOLS`); `mcp_policy` imports them, so MCP and files cannot drift apart (a test pins it, and that `FETCH_TOOLS` equals the source-record table). `core/agent/workflow_file.py` validates a file and returns the normalised document with a SHA-256 fingerprint, plain-sentence problems naming the step, and warnings; `describe_steps` gives the rows the import dialog will list. `docs/examples/workflows/access-to-care.cgworkflow.json` is a hand-written example (not exported, not run) and a test validates it. `tests/test_workflow_file.py`: 23 tests. Not built: export, import dialog, runner (stages 2 to 4). Honest limit: the rule "`confirmed` is a refusal" and "tools with their own confirmed step are not on the list" rest on the lists plus a test that no listed tool accepts `confirmed`; the schema does not advertise `confirmed`, so the validator cannot see it from the schema alone.
- 2026-11-02: stage 2 built (the export tool). `core/agent/workflow_export.py` (pure) builds a document from the recorded history the workflow report already reads: one entry per call (a call that made two layers is one step), oldest first; layers the chain did not make become roles (`@role` in every argument that equals the layer name; role name, geometry and field NAMES from the live layer); layers the chain made keep their names, because the exported steps make them again; only schema-advertised keys, never `confirmed`; a step is left out, with the reason, when its tool is not on the list or when validation refuses it (for example a path in an argument); a layer made only by a left-out step becomes a role too; a layer name inside a longer text is left alone and warned about; data sources come from the source records. The result must pass `workflow_file.validate` or the export fails loudly. `export_workflow_file` (`tools/workflow_file_tools.py`, PUBLISH) returns the whole file as a PREVIEW_REQUIRED card on the first call and writes only on the person's Confirm (`confirmed` is not advertised, so the model cannot confirm its own preview); default folder `exports/workflows`; extension forced to `.cgworkflow.json`. There is no tool that opens or runs a file, and a test pins that. 21 offline tests in `tests/test_workflow_export.py`; a live test (`tests/test_workflow_export_live.py`, written without QGIS, CI first run) exports a real buffer, checks nothing is written before confirming, and validates the written file. Tool count 297 to 298. Not built: the import dialog and runner (stage 3), the guide (stage 4). Not verified: a real export from a real session, the preview card as a person sees it, a file with several layers and many steps. Honest limit: the history records the arguments the model sent, so a step recorded with an argument the tool later repaired (a path rewritten, a name corrected) exports the model's original text.
