# PLAN-038: CLI bridge providers (master list LEAD-8)

Status: planned

## Goal
A user with a Claude Code, Codex or Gemini CLI login can run Cartogen AI with no API key. The plugin starts the installed CLI as a subprocess and uses it as the model. The plugin keeps ownership of tools, write previews, confirmations and the egress gate. Closes the "no-key use" gap in PLAN-030.

Owner confirmed the interpretation on 2026-10-28 ("start the local Claude Code, Codex or Gemini CLI login"): a model provider backed by a local CLI, our own implementation, prior art studied first.

## Prior art (researched 2026-10-28 from public pages; nothing was run)
| Project | What it does | Use to us |
|---|---|---|
| ljdstechva/qgent-cli (terminal agent, sibling of the QGent QGIS plugin) | Drives `claude -p` / `codex exec` one turn at a time, resumed by session id, "your existing subscription, no API key". Its Claude backend (per its `backends/claude.py`) runs `-p --output-format stream-json --verbose --include-partial-messages --mcp-config <file> --strict-mcp-config --append-system-prompt-file <file> --permission-mode acceptEdits --allowedTools/--disallowedTools`, parses `system/init`, `stream_event`, `assistant`, `user`, `result` events, and gives the CLI the QGIS tools through MCP. | Design B below. No licence file found on the pages read, so we copy nothing; we write our own from the CLI vendors' documentation. |
| vagnertxr/gemini_assistant (QGIS plugin, GPL-2.0) | Calls the globally installed Gemini CLI from a dock widget; user sets the executable path; Google API key or OAuth login; a `# QGIS_RUN` marker runs generated PyQGIS. | Confirms the Settings shape (executable path, login check). Its run-generated-code approach is exactly what our gates exist to avoid. The file that launches the CLI was not read (page showed only the entry point); verify before citing. |
| nkarasiak/qgis-mcp, wiseman/qgis_mcp, QGIS Agent MCP, Copla | The reverse direction: an MCP client (Claude Code, Codex, Gemini CLI) drives QGIS. | That is PLAN-034, not this plan. |
Finding: no existing QGIS plugin found that uses the Codex or Gemini CLI as a no-key model with the plugin's own tool loop. Our design A is therefore new work, not a port.

## Design
Our provider contract is small: `complete(messages, tools=None, max_tokens=None)` returns `{"message": <assistant message with optional tool_calls>, "model", "usage"}` or `{"error": ...}` (see `providers/ollama.py`). A CLI provider must fit that.

Design A (build first): CLI as a text model, plugin owns the loop.
- The provider renders `messages` plus the tool schemas into one prompt and asks for a single JSON reply: either final text or a list of tool calls. It parses that back into the standard `message`/`tool_calls` shape. The orchestrator, dispatcher, previews, confirmations and egress gate run unchanged.
- CLI built-in tools are switched off so it cannot act outside our gates. Claude: `-p --output-format json --tools "" --no-session-persistence --max-turns 1` and a strict MCP config pointing nowhere. Codex: `codex exec --json --sandbox read-only --skip-git-repo-check` with the prompt on stdin (`-`) and `--output-schema` for the reply shape. Gemini: `-p --output-format json`; the flag to disable tools is not in the headless page and must be read from its CLI reference before the adapter is written.
- Cost: a fresh process per turn; no session resume in the first version (history is already in `messages`).

Design B (later, after PLAN-034): CLI as the agent, plugin tools reached over MCP. Faster per task, but our loop guards, router and plan gate would be bypassed, so it needs the MCP server's gates first. Not part of this plan's acceptance.

## Scope
In:
1. `infrastructure/providers/cli_bridge.py`: a shared runner (argument list only, no shell, timeout, stdout size cap, kill the process tree on cancel, environment scrubbed of our own keys) plus three small adapters (command builder and output parser each).
2. A tool-call prompt and a strict parser: prose around the JSON is tolerated, a malformed block is reported as an error (never guessed), an unknown tool name is rejected.
3. Settings: provider choice, executable path with PATH detection, version and a "logged in?" check by a harmless call; the plugin never reads or stores CLI credentials or token files.
4. Egress and sensitivity labels apply exactly as for a cloud provider (data leaves the machine through the vendor's service). Settings states this once.
5. Usage footer says "estimated" unless the CLI reports tokens; the request cap works on request count.
Out: installing or bundling a CLI; reading `~/.codex/auth.json` or similar; the CLI's own agent loop or file/shell tools; Windows beyond PATH lookup in the first release.

## Open questions (owner)
1. Terms of use. Codex's docs say API-key auth is the recommended default for automation and advise against ChatGPT-managed auth for public or open-source repositories; we have not read Anthropic's or Google's current terms on third-party programs driving a subscription CLI. Read each before shipping its adapter; if a vendor disallows it, that adapter is dropped, not worked around.
2. First adapter. Recommendation: Claude Code, then Codex, then Gemini.
3. Reliability bar. The spike decides whether per-turn start-up time and JSON-in-text tool calls are good enough for multi-step plans.

## Acceptance
1. Offline: the runner refuses a shell string, enforces timeout and size cap, kills on cancel, and scrubs the environment; each adapter's command line is asserted exactly (tools disabled).
2. Offline: parser cases above; with the CLI mocked, a write tool still returns `PREVIEW_REQUIRED` and nothing changes without confirmation.
3. Spike report (CI cannot run a logged-in CLI): on the owner's machine, the nine OWN-15 rows run on the CLI provider, with latency per turn and the failures written down. Not claimed verified before that.

## Guard tests
To be written: `tests/test_cli_bridge_runner.py`, `tests/test_cli_bridge_adapters.py`, `tests/test_cli_bridge_tool_calls.py`.

## Rollback
Opt-in provider only; removing the module and its Settings entry restores today's behaviour. No stored data format changes.

## Status log
- 2026-10-28: plan written at the owner's request.
- 2026-10-28: owner confirmed the interpretation and asked for a plan from existing implementations. Prior-art research done from public pages (table above); no code copied. Next: owner answers the terms question; then build the runner and the Claude adapter offline-first and hand the owner a spike script. Nothing built yet.
- 2026-10-28: built (CI-only, nothing run against a real CLI): `providers/cli_bridge.py` (runner: argument list only, timeout, output cap, cancel, process-tree kill, provider keys scrubbed from the environment; prompt builder; strict reply parser; Claude Code adapter with `--tools ""`, `--strict-mcp-config`, `--no-session-persistence`, `--max-turns 1`, system prompt from a temp file, prompt on stdin, run in an empty temp folder), `tests/test_cli_bridge_runner.py` (real subprocess stand-in), `tests/test_cli_bridge_adapters.py`, ledger entry, and `tools/cli_bridge_spike.py` for the owner. Not yet selectable in Settings or the orchestrator; wiring waits for the spike. Open for the spike to settle: whether `--output-format json` has the documented shape on the installed version, whether `--max-turns 1` and `--tools ""` are accepted together, whether the CLI still loads user-level settings or hooks from the home folder (`--setting-sources` / `--bare` not yet tried), latency per turn.
- 2026-10-28: Codex adapter built (CI-only, nothing run against a real Codex): `codex_argv` (`exec --json --sandbox read-only --skip-git-repo-check --ephemeral --ignore-user-config --ignore-rules`, prompt on stdin via `-`), `parse_codex_events` (answer = last `item.completed` / `agent_message`; usage from `turn.completed`, reasoning tokens counted as output) and `CodexCliClient`; the client flow moved into a shared `_CliClient` base so Claude and Codex differ only in command line and parser. Difference from Claude: Codex has no documented switch that removes its shell tool, so a run in which it ran a command, edited a file, called an MCP tool or searched the web is rejected as an error rather than accepted; whether that is too strict in practice is for the spike to show (`tools/cli_bridge_spike.py --cli codex`). Unverified: that `--ignore-user-config` leaves the saved login usable (auth is believed to live apart from `config.toml`), that `--ephemeral` and `--ignore-rules` exist on the installed version (the OpenAI page names them; the flag reference was not read), the `--model` flag name, and the event names on older Codex versions (a third-party source says versions before 0.44 used different field names). Gemini adapter not started: its tool-disable flag is still unread.
- 2026-10-28: Gemini adapter built (CI-only, nothing run against a real Gemini CLI): `gemini_argv` (`-p <fixed text> --output-format json --approval-mode plan [--model m]`, full prompt on stdin), `parse_gemini_result` (reads `response`, `stats`, optional `error`) and `GeminiCliClient`. Gemini API keys are scrubbed from the environment so the CLI uses its own Google sign-in. Read from the Gemini CLI repository docs (cli-reference.md, headless.md): they give NO flag that removes the built-in tools (only a `tools.core` allowlist in settings.json, which we do not write into the user's config), so like Codex a run is rejected when the statistics show tool calls. Unverified, and for the spike (`tools/cli_bridge_spike.py --cli gemini`): that `plan` mode behaves read-only in headless runs; that `stats.tools.totalCalls` and `stats.models.<name>.tokens.prompt/candidates` exist (the docs name `stats` but not its fields; if absent, tool calls would go undetected and usage falls back to an estimate); how stdin combines with `-p` (documented as appended; the order is not stated, so the fixed `-p` text is order-neutral); and which exit code means "not signed in". All three CLI adapters now exist; none is selectable in Settings yet.
