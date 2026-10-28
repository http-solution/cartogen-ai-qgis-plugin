# PLAN-034: an MCP server over the existing tool gates (master list RM-F)

Status: planned

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
