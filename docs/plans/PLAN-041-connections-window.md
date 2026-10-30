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
