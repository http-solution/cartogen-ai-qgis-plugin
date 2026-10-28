# PLAN-038: CLI bridge providers (master list LEAD-8)

Status: planned

## Goal
A user with a Claude Code, Codex or Gemini CLI login can run Cartogen AI with no API key: the plugin starts the installed CLI as a subprocess and uses it as the model, while the plugin keeps ownership of tools, write previews, confirmations and the egress gate. This closes the "no-key use" gap in PLAN-030.

Interpretation to confirm with the owner: "CLI bridge" = a model provider backed by a local CLI. If the owner meant the reverse (a command-line way to drive the plugin, or MCP clients such as Claude Code driving QGIS), that is PLAN-034 and this plan shrinks to a note.

## Scope
In:
1. A provider class beside `claude.py`/`ollama.py` under `infrastructure/providers/`, one adapter per CLI, sharing a small subprocess runner (no shell, argument list only, timeout, output size cap, cancel kills the process tree).
2. The CLI is only a text-in/text-out model. The plugin passes the tool schemas in the prompt and parses the tool call back; the CLI's own file, shell and web tools are switched off by flags so it cannot act outside the plugin's gates.
3. Detection: find the executable on PATH, show version and "logged in / not logged in" in Settings; never read or store the CLI's credentials.
4. Egress and sensitivity labels apply exactly as for a cloud provider (the data leaves the machine through the vendor's service).
5. Usage and cost: tokens are not reliably reported, so the footer says "estimated" and the cap works on request count.
Out: bundling or installing a CLI; reading CLI token files; using the CLI's own agent loop or tools; Windows paths beyond `where`/PATH lookup in the first release.

## Open questions (owner)
1. Terms of use: whether each vendor permits driving a subscription CLI from a third-party program. Read each vendor's current terms before building; if not allowed, that adapter is dropped, not worked around.
2. Which CLI first (recommendation: Claude Code, since the tool-calling prompt is already tuned for Claude).
3. Reliability bar: CLI start-up latency per turn and unstructured tool-call output may make long plans unusable; a spike measures this before commitment.

## Acceptance
1. Offline: runner refuses a shell string, enforces timeout and size cap, kills on cancel; tool-call parsing handles prose around the JSON, a malformed block (reported, not guessed) and an unknown tool name.
2. Offline: with the CLI mocked, a write tool still returns `PREVIEW_REQUIRED` and nothing changes without confirmation.
3. Hand (owner): the nine OWN-15 rows pass on the CLI provider, or the failures are written down. Not claimed before that.

## Guard tests
To be written: `tests/test_cli_bridge_runner.py`, `tests/test_cli_bridge_tool_calls.py`.

## Rollback
The provider is opt-in and selectable only in Settings; removing the class and its Settings entry restores today's behaviour. No stored data format changes.

## Status log
- 2026-10-28: plan written at the owner's request to prioritise CLI bridges. Nothing built. Next step is a one-day spike (Claude Code adapter, latency and tool-call reliability measured on the smoke fixtures) once the owner confirms the interpretation and the terms question.
