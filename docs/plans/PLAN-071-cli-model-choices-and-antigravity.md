# PLAN-071: Model choices on the CLI pages, and an Antigravity CLI (agy) connection

Status: in progress

## Goal
Two owner requests (2026-11-09, after the first real Windows check of the Codex page, OWN-16): "I can not select the model to use" and "add antigravity cli".

## Scope
1. **Model choices.** The model box on each CLI page is an editable drop-down, but the Codex one held only "auto": nothing to select. Now: Claude Code keeps its three aliases (sonnet, opus, haiku); Codex gets the two names OpenAI's models page gives verbatim (`gpt-6.1-sol`, `gpt-6.1-terra`); Antigravity gets the one slug Google's headless page uses in its own example (`gemini-3.8-flash-medium`) and, once the program is found, its real list from `agy models` (documented: one slug per line, then a display name). The box stays editable, so a name that is not listed can still be typed. Names change often; the lists are seeds, not a promise.
2. **Antigravity CLI connection (LEAD-10, owner decision 2026-11-03: build it).** `agy_cli`, experimental and off unless "Allow CLI logins" is ticked, like the other two. It runs `agy --input-format stream-json --output-format stream-json --sandbox [--model SLUG]` in an empty temporary folder with the prompt on standard input as one `{"event":"user","message":{"content":...}}` line (documented in Google's headless page; a prompt on the command line would hit the Windows length limit). The reply is the `result.response` of the final `result` event. Tool use: agy's default in a headless run is that anything needing approval is soft-denied; the plugin never passes `--dangerously-skip-permissions`, adds `--sandbox`, and, like the Codex adapter, rejects a run in which agy used a tool of its own (`step_update` with `step_type` `tool`). Sign-in: agy has no documented sign-in status command, so the state reads "sign-in not confirmed" and Connect (one short test question) is the real test; "Sign in" opens a terminal running `agy`, which starts its own browser sign-in.
3. Registered everywhere the other two are: settings keys, Connections catalog and dialog, program finder (`agy`, and `%LOCALAPPDATA%\agy\bin` on Windows), status and install commands (from Google's quick-start), dock label, orchestrator.

## Not done, said plainly
- **Not run against a real agy, ever.** The earlier plan said no provider code before a real run; the owner has since asked for it, and this is built from Google's published pages (antigravity.google/docs/cli/headless, /reference, /getting-started, read 2026-11-09), so it carries the same "experimental, not verified" labels as the other two. Third-party reports say `agy -p` printed nothing when its output was not a terminal on v1.0.6; the stream-json path used here is the documented non-terminal route, but only a real run shows it works. `tools/agy_probe.py` stays the way to check a machine.
- Whether agy's read-only tools run without approval (so a plain question could trigger a `tool` step and be rejected) is unknown until a real run.
- The Codex model names beyond the two verbatim ones are not listed: the page's remaining names came through a summary, not the page text, and third-party guides disagree.
- `--effort` is not exposed (the two Google pages disagree on its values).

## Acceptance
Offline tests pass (`tests/test_agy_cli.py`, the updated provider-settings, status and catalog tests); ruff, mypy, ledger guard and master-list check pass; CI live job passes. Live, by hand, on a machine with agy: the page finds the program, the model list fills from `agy models`, Connect answers or says what failed, and one chat message round-trips. Until then the row stays "built, not verified".

## Guard tests
`tests/test_agy_cli.py`; ledger entry `agy-cli-provider` and the existing `cli-bridge-*` entries.

## Rollback
Untick "Allow CLI logins" (the provider disappears), or revert the commit. A saved `agy_cli` provider with the switch off falls back to the default like the other two.

## Status log
- 2026-11-09: opened from the owner's request. Research read from Google's and OpenAI's own pages; nothing run against a real agy.
- 2026-11-09: built. Offline: 24 new tests in tests/test_agy_cli.py plus four live tests (CI only, first run) for the model drop-down; full suite at the 54-error baseline (no 'requests' here), ruff, mypy, ledger guard and master-list check clean. Nothing run against a real agy. Held back from pushing until records PR 589 (same branch) is merged.
- 2026-11-09 (later): PR 589's CI did not complete on either head (ecd8207, 229d281): the `tests` and `docs-site` runs and the CodeQL default setup ended as failures with most jobs never created (only secret-scan, service-reach and the two 3.11 test jobs ran; no QGIS live job, no 3.10 job, no build, no Python or JavaScript CodeQL), and one re-run of the `tests` run did the same. No job logged a failure, the same workflow had passed on a docs-only head of PR 588 an hour earlier, and githubstatus.com reported no incident. Treated as a platform fault, not a test failure; not merged on partial checks. A fresh run is started by this status-log commit.
