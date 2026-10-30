# PLAN-041: A Connections window for APIs and CLIs

Status: in progress

## Goal
The model connection (hosted API keys, Ollama, a signed-in CLI such as Claude Code, Codex or Gemini) has its own window with its own menu link, so a user can see every connection, set one up, test it and choose which one is in use without going through the long Settings dialog.

## Why
Owner request, 2026-10-30 ("i dont like how you structured the API and CLI connection in the settings; i propose a new menu link and new window for connections"). Settings section 01 mixed choosing a connection with looking at its page: clicking a pill both showed the page and made it the active connection, which is why "how do I choose the active connection" was not obvious.

## Decisions (owner, 2026-10-30)
1. Move, not copy: section 01 "Where your prompts go" and 02 "Keys" leave Settings. Settings keeps privacy, behaviour, print layout and diagnostics (renumbered 01 to 05) and a "Connection in use: X" row with a Connections... button.
2. Layout: list on the left, the selected connection's page on the right.
3. Entry point: Plugins > Cartogen AI > Connections... (opens the panel first, so the panel's provider dropdown refreshes). Settings also opens it.

## Scope
In:
1. `core/ui/connections_catalog.py` (Qt-free): the provider table, CLI table and groups, moved out of settings_dialog.py unchanged.
2. `core/ui/connections_dialog.py`: the window. List rows carry a mark (set, verified this session, empty) and an "(in use)" tag; looking at a page and using a connection are separate actions (`_show_provider`, `_use_provider`); the CLI acknowledgement box sits under the CLI heading and gates the rows and their Use buttons; NASA FIRMS key on its own page under "Data services"; Test / Check connection / Sign in / Manage account unchanged in behaviour.
3. `core/ui/theme_palette.py`: the palette helper both windows use.
4. Settings: connection widgets, state, methods and the provider part of `accept()` removed.
5. Dock: `open_connections`; the dropdown refresh shared by both windows.
Out: no setting key, credential storage or default changed; no change to how the agent picks the provider.

## Acceptance
1. Offline: catalog imports without Qt; source checks for the show/use split, what Save writes, the menu action and the dock refresh; Settings no longer references connection widgets.
2. CI live: window builds with a row, page and Use button per connection; clicking a row does not change the connection in use; typed key changes the mark and OK saves key, choice and model; FIRMS key saves from its page; Settings shows the connection in use and its OK never overwrites the choice; the existing CLI and Test-button live tests run against the new window.
3. Hand (owner): open the menu link, look at every page at a normal and a small window size, press Use this connection and OK, check the panel dropdown, run Check connection and Test. Not claimed before that.

## Guard tests
`tests/test_connections_window.py`, `tests/test_connections_window_live.py`, `tests/test_cli_provider_settings.py`, `tests/test_cli_provider_settings_live.py`, `tests/test_api_test_button_live.py`, `tests/test_settings_sections.py`, `tests/test_provider_check.py`.

## Rollback
Revert the PR: connections return to section 01 and 02 of Settings.

## Status log
- 2026-10-30: built at the owner's request. CI-only; the window has never been opened by a person and its layout is unseen (a wrapping custom layout froze QGIS before, so only plain vertical and horizontal layouts are used). Replaces the Keys summary list with the marks in the connection list. The mark for a CLI is "set" only when its program is found on this computer.
- 2026-10-30: slice 2 at the owner's request ("i want the connection detect any available CLI subscription automatically"). On open, and on "Detect again", the window looks for the Claude Code, Codex and Gemini programs on a background thread and shows one line each in "Found on this computer": found or not, version, and whether the user is signed in. Signed in is read with no model call: `codex login status` (its "Logged in using ChatGPT" wording is from the owner's machine), `claude auth status` (assumed JSON with `loggedIn`; not run here), and for Gemini only whether `~/.gemini/oauth_creds.json` exists (never read; "probably signed in"). Anything unreadable shows as "sign-in not confirmed", not a guess. A signed-in CLI gets a Use button, enabled only after the CLI acknowledgement box is ticked. Decision: detection never switches the connection by itself, because a CLI sends the conversation to that vendor and the user must choose that. Also searched: `%LOCALAPPDATA%\Microsoft\WinGet\Links`. CI-only: no signed-in CLI was available, so `claude auth status` and the Gemini check are unverified.
- 2026-10-30: redesign after the owner's screenshot of the first build ("the worst design i ever seen"). Faults seen in it: the list was a column of buttons that all rendered in the same brand blue, so the selected row could not be told apart; it was squeezed to a few rows under a tall header and the detection panel; "Hosted" appeared twice because the provider table is not ordered by group; and Codex showed "not found". Now: the list is a native QListWidget (one heading per group, bold "in use" row, marks with a legend), the header is two lines, detection is written on each CLI page and into the list mark instead of a top panel, only "Use this connection" is the filled button, CLI pages can always be read and only their Use button waits for the acknowledgement. Detection falls back to the program's usual name when a saved path no longer exists and puts the real path in the field. Rendered offscreen with PyQt6 (no QGIS, Fusion style, fake settings) and looked at; the real QGIS theme and fonts have still not been seen. Codex "not found" on the owner's machine is not explained: the path `...\Programs\OpenAI\Codex\bin\codex.exe` exists per Get-Command; this build shows what was looked for.
- 2026-10-30: style pass after rendering the window in a dark palette and at the smallest size (offscreen PyQt6, not QGIS). One accent now: "Use this connection", the selected row and OK are the brand teal (dark mode had mixed the theme's blue with the teal); Cancel keeps normal text colour with a teal border (teal text looked disabled on dark); the detection line on a CLI page drops the program's name, which the page title already gives, so it stays on one line at 780 px. No other brand's design system was applied: this is a native QGIS dialog that must follow the user's own theme.
