# PLAN-064: One retry when the CLI model names a tool that was not offered (DEF-33)

Status: in progress

## Goal
Round 3 (rows B1 prompt 5 and B2 prompt 8, Claude Code CLI) ended two tasks on "[API error] The model asked for a tool that is not available" after the model named `execute_pyqgis_script` and `import_humanitarian_table`, neither offered in that request. The task should continue with the tools that exist, without the plugin ever running a tool it did not offer.

## Scope
`src/cartogen_ai/infrastructure/providers/cli_bridge.py` only: `parse_reply` raises `CliToolUnavailableError` (a `CliBridgeError`), and `_CliClient.complete` asks once more with a correction naming the offered tools. A second unknown tool is the same error as before. Other providers use native tool calling and are not touched.

## Acceptance
`tests/test_cli_bridge_adapters.py::TestUnofferedToolGetsOneRetry` passes; the strict-parser test `test_unknown_tool_is_an_error_not_a_guess` still passes; ruff and the ledger guard pass. Live check: rerun rows B1 prompt 5 and B2 prompt 8 with the Claude Code CLI after release.

## Guard tests
`tests/test_cli_bridge_adapters.py` (TestParseReply, TestClaudeCliClient, TestUnofferedToolGetsOneRetry).

## Rollback
Revert the commit; the bridge returns to failing at once on an unknown tool.

## Status log
- 2026-11-08: built and tested offline (CI only, not seen live). Cost: one extra CLI call, only when the model named an unoffered tool.
