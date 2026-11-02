# PLAN-050: Hand-test package for the 1.18.5 features

Status: in progress

## Goal
The ledger lists eight features that are "not hand-tested" (result checks on computed and fetched layers, the fetched-data source record, the verified workflow report, ranked HDX search, the MCP server and its approval dialog, workflow export and import). This plan gives whoever tests them rows that say exactly what to type, which files go in and come out, what evidence to save and how to judge it, and scripts that do the measurable part so only the human part is left for a person.

## Scope
Test tooling, rows, fixtures and an operator guide only. No plugin behaviour changes. Out of scope: running the rows (needs QGIS and a person), a real MCP client beyond an optional manual step, fixing anything the rows find.

### What was built (2026-11-02)
- Rows W1 to W12 in `docs/HAND_TEST_V2_ROWS.json`, each with `inputs`, `outputs`, `pass_if`, `cost`, and `expected_tools` where a tool is judged. The bundle builder prints them in `3_SHEET.md`.
- `tools/mcp_probe.py`: drives the local MCP server as a client (refusals, tool lists, a read, a SENSITIVE read, a denied write) and saves `mcp_probe.json/.md` without the token.
- `tools/check_workflow_file.py`: runs the plugin's own validator and a leak scan (paths, keys, emails, coordinate lists, URLs with keys) on any `.cgworkflow.json`.
- `tools/collect_evidence.py` now also saves every `cartogen/*` layer property (`layer_properties.json`): checks, sources, lineage.
- `tools/check_evidence.py` now lists the plugin records each layer holds and the probe's failed checks.
- Fixtures in `docs/hand_test_v2_inputs/`: one runnable workflow file, one egress-stop file, six broken files.
- Bundle: `python tools/build_hand_test_v2.py --plugin-zip dist/cartogen_ai_v<version>.zip` now adds `6_tools/` and the fixtures.
- Operator guide: `docs/HAND_TEST_PACKAGE_1.18.5.md`.
- Tests: `tests/test_hand_test_package.py` (probe against the real in-process server, checker against the fixtures, row completeness, evidence reader).

## Acceptance
- Offline: `tests/test_hand_test_package.py` and `tests/test_hand_test_v2.py` pass; the bundle builds; the probe passes all 11 of its checks against the real in-process server; every shipped fixture is accepted or refused as its row says.
- Real: one person or agent runs rows W1 to W12 in QGIS 4.2 and sends back `results/`; each row gets Pass, Partial, Fail or Skip with evidence. Until then the package is CI-only.

## Guard tests
`tests/test_hand_test_package.py`, `tests/test_hand_test_v2.py`.

## Rollback
Remove the W rows from `docs/HAND_TEST_V2_ROWS.json`, the new tools and fixtures; the bundle builder falls back to the v2 rows. Nothing else depends on them.

### Not verified
Nothing here has been run inside QGIS. The probe was run against the real server code with a fake tool call and no QGIS; the real `run_allowed_tool` outside QGIS stops at the egress gate, so a write that is allowed could not be tried. `layer_properties.json` capture in `snap()` is untried. The expected fingerprint in row W9 is computed from the fixture offline (a test pins it) but whether the lineage entry stores that value is read from the code, not seen. Row W11's expected behaviour is a prediction from the egress design; the row says to record what really happens.

## Status log
- 2026-11-02: package built, offline tests and ruff green. Ledger `hand_row` of the eight features now names the W rows. Waiting for a first run.
