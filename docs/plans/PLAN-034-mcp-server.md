# PLAN-034: an MCP server over the existing tool gates (master list RM-F)

Status: in progress

## Goal
Other AI clients (Claude Desktop, Claude Code, Cursor, Codex and the like) can drive QGIS through this plugin's tools, and every write still goes through the plugin's confirmation, egress and sensitivity gates. Four of the flagship plugins in the analysis document expose MCP; none of them has this plugin's gates, so the safe version is the differentiator.

## Scope
In:
1. A local server bound to 127.0.0.1 only, off by default, switched on in Settings with a one-line warning, with a random per-session token the client must present.
2. The transport is a thin layer over `TOOL_REGISTRY`: list tools (the router's top-k and `find_tools` discovery mean a client is not handed 296 schemas at once), call a tool, return its result.
3. A call that would write, delete, export or send data goes through the same preview and confirmation as in chat. With no human present at the plugin, the call returns the preview and waits; it is never auto-confirmed by the client.
4. Layers tagged RESTRICTED or SENSITIVE are never returned to a client that is not local, and the egress gate applies to anything leaving the machine.
5. Requires PLAN-031 first, so exposed tools carry `checks`.
Out: remote (non-loopback) access; auto-confirm; exposing the arbitrary-script tool; a hosted service (tier question, CLAUDE.md).

## Acceptance
1. Offline: a request without the token is refused; a write tool called without confirmation returns `PREVIEW_REQUIRED` and changes nothing.
2. CI live: list, a read call and a write call (preview only) against a real QGIS project.
3. Hand (owner): Claude Desktop lists the tools, runs a read, and is stopped at a write until the user confirms in QGIS.
Security review before release: threat model written into the status log (token handling, DNS rebinding, a second local process on the port).

## Guard tests
To be written: `tests/test_mcp_server.py`, `tests/test_mcp_server_live.py`.

## Rollback
The setting is off by default; remove the module to roll back.

## Status log
- 2026-10-28: plan written. Depends on PLAN-031. No code.
- 2026-11-02 (owner said go; FIRST SLICE built, read-only): `core/agent/mcp_policy.py` (pure: allowlist, request checks, JSON-RPC handling), `core/agent/mcp_server.py` (stdlib HTTP on 127.0.0.1, POST /mcp, JSON replies only), a menu item "MCP server (local, read-only)..." in `plugin_main.py`. Decisions taken in this slice, each a departure or narrowing of the plan above:
  * **Read-only.** 24 tools are on an explicit allowlist (layer, attribute, extent, metadata, QA, list tools, `find_tools`); every other tool, write or not, is refused with `NOT_RUN` and nothing runs. The plan's acceptance 1 ("a write tool returns PREVIEW_REQUIRED") is replaced by "returns NOT_RUN and changes nothing", because there is no approval path: a preview that nobody can confirm would be misleading. Of the 83 READ-classified tools many are not safe to hand out (`run_steps` runs other tools, the grounded searches spend the user's API key, `extract_pdf_tables` reads disk files, `geocode_*` and `web_research` send text out, `select_*` and `set_map_view` change what the user sees), so the list is written out, not derived.
  * **Gate.** Every call goes through the egress gate in ENFORCE mode with the client counted as non-local, whatever the user's own setting is; a gate that cannot decide refuses. Arguments the tool does not advertise are dropped (no `confirmed`). A RESTRICTED or SENSITIVE layer, or one derived from it, is refused; there is no override.
  * **Started by a person, every time.** Menu item, plain warning, the token shown once; nothing is saved; QGIS restart means off. Ephemeral port.
  * **Threat model (written for this slice; not independently reviewed).** (1) A web page in the user's browser calling the port: refused by the Host check (DNS rebinding sends the attacker's host name), by the Origin check (only the server's own origin), and by the token, which a page cannot read. (2) Another local process on the same machine: can connect to the port but needs the 256-bit token, which exists only in the menu dialog and the client's config; any process running as the same user can read that config or the clipboard, so this protects against other users and browsers, not against malware running as the user. (3) A rogue process squatting a fixed port: avoided by an ephemeral port per start, so a client configured for an old port gets a refusal, not a stranger's answer; the cost is re-adding the client after every start. (4) Token in the clipboard/command line: shown once; `claude mcp add` stores it in the client's own config. (5) Data a client reads goes to that client's AI service: the dialog says so; sensitive layers are blocked but INTERNAL and PUBLIC ones are not. (6) Large replies: capped at 200,000 characters; request bodies at 1 MB. (7) Denial of service by a local client: not defended (the server is threaded, a tool runs one at a time on the main thread, a slow tool blocks QGIS for its duration).
  * **Not verified.** The protocol is implemented from the MCP specification text; it has NOT been tried with Claude Desktop (which spawns stdio servers and would need a bridge such as `mcp-remote` for HTTP), Claude Code or Cursor. The live test (CI first run) runs the real tool on the main thread through the existing dispatcher. The menu dialog code was never run.
  * **Next slice (needs an owner decision):** an approval path for writes: a QGIS-side dialog "Client wants to run TOOL with ARGS, allow once?", never auto-confirmed. Until then, writes over MCP do not exist.
