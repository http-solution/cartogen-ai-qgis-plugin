# PLAN-053: The plugin knows what it runs on, and works on every PC that runs a current QGIS

Status: in progress

## Goal
The owner's requirement (2026-11-03): the application must work on every PC and every version it meets, so it has to detect the version instead of assuming one. Today (read 2026-11-03) the plugin reads no QGIS version at run time (only QGIS's own install gate applies: `qgisMinimumVersion=4.2`, `qgisMaximumVersion=4.99`), finds the Claude and Codex CLIs per operating system and shows each CLI's version but never uses it, and nothing records the machine in a log or an evidence folder, so a failure on another computer cannot be read afterwards. "Every version" is read together with the owner's decision of the same day: support only the latest QGIS (4.2 and later), any OS, any CLI version.

## Scope
Stage 1 (this change):
- `core/environment.py`: `detect()` (QGIS, Qt, GDAL, Python, OS, architecture; blank when unreadable), `describe()` (one line), `findings()` (unsupported: QGIS before 4.2, Python before 3.10; untested: QGIS 5 or later, an OS other than Windows, macOS, Linux; note: unreadable QGIS version) and `startup_message()`.
- A start-up check in `plugin_main` that logs the machine (versions only: no user name, host name, path or locale) and shows one warning when something is unsupported or untested. It never stops the plugin from loading.
- The machine in every evidence folder's `context.json`, and a "This computer" line in the Help.
Stage 2 (built, PR after stage 1): version-aware CLI adapters for Claude Code and Codex. Not a table of flags by version number (the plugin cannot know every version's flags): the command runs as before, and only when the CLI itself says it does not know a flag does the bridge act. `infrastructure/providers/cli_flags.py` holds the tables: REQUIRED flags (tools, MCP servers, slash commands, sandbox, user config and rules, output format, the prompt, the chosen model) are never left out; the run stops with a message naming the flag and the CLI version. DROPPABLE flags (`--no-session-persistence`, `--max-turns`, `--ephemeral`, `--skip-git-repo-check`) are left out for one more run, the user is told what that means, and it is remembered for that program file. Still to do: the Antigravity (`agy`) adapter, which needs the real probe (LEAD-10).
Stage 3 (built): a collapsible "This computer" section in Settings (Diagnostics) with the machine in the words of a bug report and a Copy button; it starts no process, so opening Settings never waits, and the CLI versions stay in the Connections window. An unexpected tool failure that looks like a QGIS or Qt version problem (a missing attribute, import or name, or a wrong argument type, in a message that names QGIS or Qt) now carries the machine line in its result. NOT built, on purpose: a per-tool minimum-QGIS declaration and a refusal for it. No tool needs a QGIS newer than 4.2 today, so that would be machinery with no user; it is added with the first tool that needs it.
Out of scope: supporting QGIS 3.x (decided against), and any change to what a tool does.

## Acceptance
- Offline: `tests/test_environment.py` passes (parsing, detection with failing probes, the findings table, the start-up text, the three places that carry the result).
- CI live: `tests/test_environment_live.py` reads the QGIS version from a real QGIS, finds the CI image supported, and runs the start-up check without a warning.
- By hand: hand row W13 on each OS the owner has (Windows first): the Help line matches Help > About QGIS.

## Guard tests
`tests/test_environment.py`, `tests/test_environment_live.py`; ledger entry `environment-detection`.

## Rollback
Revert the change: the plugin then reads no version, as before. Nothing else depends on it.

## Status log
- 2026-11-03: stage 1 written, tests first. Not run in a real QGIS by me or anyone; the thresholds are the project's rules (QGIS 4.2 and later, Python 3.10), not measurements. The `agy` provider (LEAD-10) waits for its probe run before stage 2 can cover it.
- 2026-11-03: stage 1 merged (#558); stage 2 written, tests first (`tests/test_cli_flags.py`). Offline only: the rejection wordings in the tests come from knowledge of the CLIs' argument parsers, not from a run. Which flags are droppable is a judgement for the owner to confirm (the list errs towards refusing).
- 2026-11-03: stage 2 merged (#559). Stage 3 written, tests first: report text, machine note on version-looking failures, the Settings section. Live test written without a QGIS install. The Antigravity adapter remains, waiting on the `agy` probe (LEAD-10).
- 2026-11-03: owner confirmed the droppable-flag list as built (`--no-session-persistence`, `--max-turns`, `--ephemeral`, `--skip-git-repo-check`); every other flag stays required. Not a test result: the rejection wordings are still unverified against real older CLIs.
