# Hand-test package for the 1.18.5 features (rows W1 to W12)

For whoever runs the test: a person at QGIS, or an AI agent driving QGIS and a terminal for them. The rows themselves (exact text to type, files in, files out, how to judge) are in `docs/HAND_TEST_V2_ROWS.json` and appear in the bundle as `3_SHEET.md`. This page is the method: the order, what to save, how to keep it cheap, and what to send back.

**Status of everything below: written without a QGIS install. The scripts were run against the real server and validator code, not inside QGIS. The first real run is the first test of the package itself; if a step does not work as written, write that down as a finding, do not work around it silently.**

## What this tests, and what it cannot

| Rows | Feature | Needs | Model cost |
|---|---|---|---|
| W1, W2 | result checks recorded on a computed and a fetched layer (PLAN-043) | person, real model | 2 + 1 requests |
| W2, W3 | fetched-data source record, provenance, spatial report (PLAN-044) | person, real model, internet | 1 + 3 |
| W4 | verified workflow report (PLAN-045) | person, real model | 3 |
| W5 | ranked HDX search (PLAN-046) | person, real model, internet, browser | 1 |
| W6 | MCP server: refusals and read tools | terminal script, no model | none |
| W7 | MCP server: the approval dialog | person at the dialog | none |
| W8 | workflow export | person, real model | 3 |
| W9 | workflow import, run, traceability | person | none |
| W10 | six broken files refused | person (free pre-check by script) | none |
| W11 | egress stop in an imported workflow | person, real model | 1 |
| W12 | the guide itself | a reader who did not write it | none |

Not covered, on purpose: a real MCP client (Claude Code, Claude Desktop, Cursor) beyond `mcp_probe.py` (an optional extra, see W7), the licence table against providers, CRS and stale-field checks (switched off), the large-download preview (not built), and Cartogen's Undo for MCP changes (does not exist). Nothing here proves the model picks the right tool every time; the `expected_tools` check only shows what it did on that run.

## The efficient order (about 25 model requests in all)

1. **Free first.** Run these before opening QGIS; they cost nothing and catch package faults:
   `python tools/check_workflow_file.py docs/hand_test_v2_inputs/smoke_reach.cgworkflow.json docs/hand_test_v2_inputs/smoke_egress_stop.cgworkflow.json --expect-valid`
   `python tools/check_workflow_file.py docs/hand_test_v2_inputs/bad_*.cgworkflow.json --expect-invalid --json W10_expected.json`
   Both must exit 0. `W10_expected.json` is the sentence each bad file should give in the dialog (row W10).
2. **Set up once.** Install the zip in `1_plugin` into a fresh QGIS profile, configure ONE provider (a cheaper model is fine; these rows check the plugin's records, not answer quality), tick "Save an evidence folder for each request", copy `3_test_files` to a writable folder and open the copy of `smoke_start.qgz`.
2b. In the QGIS Python console, once per session: `exec(open(r"<bundle>\6_tools\collect_evidence.py", encoding="utf-8").read()); setup(r"<bundle>\results")`.
3. **No-model rows next: W6, W10, W9.** They need no API credit. W6 is the only row a script can run alone.
4. **Model rows: W1, W2, W3, W4, W8, W5, W11, in that order of value.** One row, one new chat (history is billed again on every call). Never chain rows in one chat: each starts from the state it names.
5. **People rows last: W7 (dialog), W12 (reader).**
6. **Finish:** save the CartogenAI log (Log Messages), run `python 6_tools/summarize_usage_log.py cartogen.log --csv usage.csv`, then `python 5_check_evidence.py <bundle>\results`.

If a model row fails because of the model's wording (wrong tool for the prompt, not a plugin fault), run it ONCE more in a new chat; a second failure is a result, not noise. Do not retry network failures more than once.

## Evidence layout (everything lands under `results/`)

```
results/
  4_RESULTS.csv            fill: Pass / Partial / Fail / Skip + one line of notes per row
  evidence/<row>/          written by snap('<row>'): log_cartogenai.txt, window.png, canvas.png, layers.txt/.json,
                           layer_properties.json (the plugin's own checks/sources/lineage on every layer), project.json,
                           plugin_evidence/ (steps.jsonl = the tools called, summary.md = the request), tools_called.txt, note.txt
  outputs/<row>/           files the row produces: reports (.md), workflow files (.cgworkflow.json), mcp_probe.json/.md, expected.json
  screens/                 screenshots a row asks for, named as the row says (W7-dialog.png, W9-dialog.png, ...)
```

Rules: use the row id exactly as the file name; snap right after the reply, before the next action; never edit a saved file; a missing item goes in the notes as "not saved: why". If `snap_errors.txt` exists, send it. Screenshots of a dialog must show the whole dialog; blank out the MCP token if it is visible.

## How a row is judged

- **Machine part:** `5_check_evidence.py` prints, per row with `expected_tools`/`forbidden_tools`, PASS or FAIL from `steps.jsonl`; lists which plugin records each layer holds (`checks`, `sources`, `lineage`); and reports the MCP probe's failed checks.
- **Pass-if part:** each row has a `Pass if` line naming the exact file and key to look at. A reader does that comparison and writes Pass, Partial or Fail.
- **Eye part:** wording, readability, whether a dialog makes sense to a non-technical person. Only a person decides these; write the one sentence that explains the verdict.
- A result with no evidence is "Skip", not "Pass".

## Per-row quick reference

| Row | Type exactly | Files in | Files out | Pass if (short) |
|---|---|---|---|---|
| W1 | severity index on smoke_admin; then setting off and a second index | smoke_start.qgz | fields only | `cartogen/checks` present after W1a, unchanged after W1b |
| W2 | fetch Yemen ADM1 from geoBoundaries | none | a layer | `cartogen/sources` with licence_checked=false, and `cartogen/checks` |
| W3 | fetch, then provenance, then spatial report | none | report file | report has "Data source:" and does not say the licence was verified |
| W4 | buffer, join, workflow report | smoke_start.qgz | 2 layers, .md | steps in order, 500 shown, unchecked layers named |
| W5 | find a dataset of health facilities in Yemen | none | reply | first result: open licence, recent, Yemen, matches HDX page |
| W6 | `mcp_probe.py URL TOKEN out --layer smoke_points --sensitive-layer smoke_zones` | running server | probe json/md | 11 of 11 checks pass; after stop it cannot connect |
| W7 | probe with `--write-tool-check --wait-for-person`, then Allow once | running server | probe json, one layer | Deny and timeout make nothing; Allow once makes one layer; SENSITIVE shows no dialog |
| W8 | buffer, join, export workflow | smoke_start.qgz | .cgworkflow.json | `check_workflow_file.py --expect-valid` exits 0 |
| W9 | open smoke_reach.cgworkflow.json, map points, Run | that file | layer with 5 features | lineage holds the file's fingerprint |
| W10 | open each bad file | six bad files | none | each dialog sentence matches `expected.json`, no layer added |
| W11 | mark smoke_zones RESTRICTED, run smoke_egress_stop | that file | none | stops at the card, nothing sent; card text recorded |
| W12 | hand over `docs/WORKFLOW_FILES.md` only | the guide | notes.txt | finished unaided, or stuck points listed |

## MCP rows (W6 and W7) step by step

1. Plugins > Cartogen AI > MCP server (local)... > read the warning > Yes. The next dialog shows the address (`http://127.0.0.1:PORT/mcp`) and a one-time token. Do not paste the token into any saved file.
2. Terminal (not QGIS), from `6_tools`: `python mcp_probe.py <address> <token> ..\results\outputs\W6 --layer smoke_points --sensitive-layer smoke_zones`. Mark smoke_zones SENSITIVE first, through the chat (it asks you to approve).
3. For W7 the dialog is the test. The probe sends a `buffer_analysis` call naming a layer that does not exist, so even an accidental Allow cannot make a layer; to see Allow once work, send a real call from a client, or with the probe's `post()` in a Python shell: `p = Probe(url, token); p.rpc("tools/call", {"name": "buffer_analysis", "arguments": {"layer_name": "smoke_points", "distance": 500, "output_name": "mcp_allowed"}})`.
4. Stop the server from the same menu item; run the probe again; it must fail to connect.
5. Optional: connect Claude Code with the `claude mcp add ...` command the dialog shows, ask it to list layers and buffer one. Record what it said. This is the only way to learn how a real client behaves; nothing else in the package does.

## Reporting a defect

One block per defect, in the notes of its row: row id; plugin version (Help panel) and QGIS version; the exact text sent; what happened; what was expected; the evidence file names. Do not diagnose and do not fix in the same pass. The owner turns each defect into a failing test first (CONTRIBUTING).

## Sending results back

Send the whole `results/` folder, the saved CartogenAI log, and `usage.csv`. The checker's output is in `5_check_evidence.py`'s terminal text; paste it into the reply.
