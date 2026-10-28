# PLAN-039: Settings connection redesign and the CLI panel (master list LEAD-9)

Status: in progress

## Goal
The Settings window groups connections by what the user is actually choosing (where do my prompts go, and what do I bring) and lets a user set up, test and sign in to a CLI provider without leaving it.

## Scope
In (this slice, section 01 "Where your prompts go" only):
1. Three groups with a plain heading each: Hosted (you bring an API key), Local (nothing leaves this machine), Your own CLI login (experimental). Replaces the flat pill list; same plain vertical layout (a wrapping custom layout froze QGIS once, see the comment in the dialog).
2. The CLI group carries its own acknowledgement box. Its pills are listed but disabled until it is ticked, so there is no "reopen Settings to see them" step (this replaces the opt-in box added in PLAN-038 step 4). Unticking while a CLI provider is active moves the choice back to the default provider. The saved flag keeps its meaning: `normalize_provider` ignores a saved CLI provider while it is off.
3. Each CLI page shows a live status line (program found or not, no subprocess) and two buttons: Check connection (finds the program and its version, then asks one tiny question through the same client the agent uses, on a background thread) and Sign in... (opens a terminal running the program's own sign-in). A failure says which step to fix: program name/path, or sign-in.
4. The Qt-free logic lives in `providers/cli_bridge_status.py` so it is testable without QGIS.
Out, for later slices: reordering sections 02 to 04, an "Advanced" fold for the rarely used settings, a Test button for the API-key providers (the model-list fetch already does that job), hand-test protocol rows.

## Acceptance
1. Offline: status helpers against the Python interpreter as a stand-in program and mocked model calls; terminal command per platform; unsafe paths never reach a launcher; dialog wiring from source.
2. CI live: the dialog builds with the box off (pills disabled) and on; ticking enables the pills with no reopen; Save writes the path as a plain setting and nothing to the credential store; unticking falls back; results update the status line and buttons.
3. Hand (owner): open Settings, tick the box, press Check connection with each CLI signed in and signed out, press Sign in..., and look at the layout. Not claimed before that.

## Guard tests
`tests/test_cli_bridge_status.py`, `tests/test_cli_provider_settings.py`, `tests/test_cli_provider_settings_live.py`.

## Rollback
Revert the PR: Settings returns to the flat list and the PLAN-038 opt-in box.

## Status log
- 2026-10-28: plan written and slice 1 built at the owner's request ("integrate the CLI bridge and authentication in the settings window, redesign the settings to make some logic"). CI-only. The terminal launch is untested on every platform and attempted only for plain-character program paths; otherwise the command is shown to run by hand. `--version` is assumed to exist on all three CLIs. Sections 02 to 04 unchanged.
