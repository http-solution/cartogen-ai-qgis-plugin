"""What an outside AI client may do over MCP, and how a request is judged (PLAN-034, roadmap step F, first slice). Pure: no sockets, no QGIS.

Two tiers. READ tools (ALLOWED_TOOLS) run at once: they show field names, counts, statistics, extents, metadata and QA status of the open project,
never feature values. WRITE tools (WRITE_TOOLS) run only after a PERSON approves that exact call in a dialog inside QGIS ("allow once"; the default
button is Deny, there is no "always allow", and a dialog nobody answers denies). If the server was started without an approval function, writes are
refused as before. Every other tool is refused and nothing runs.

The WRITE list is deliberately short and written out: analysis tools that make a NEW layer from existing ones, and presentation-only styling and
visibility. Left out on purpose: tools that edit existing data (`set_attribute_value`, `add_field`, ...), delete anything, write to a path the client
names, reach the network, run code, or have their own `confirmed` step (that confirmation is the plugin chat's and is not the same as this approval).

The tool list is an ALLOWLIST written out below, not "every READ tool". Of the 83 tools classified READ, many are not safe to hand to an outside
client: `run_steps` runs other tools, the grounded-search tools spend the user's API key, `extract_pdf_tables` and friends read files from disk,
`geocode_*` and `web_research` send text to outside services, and `select_*`/`set_map_view` change what the user sees. A tool that is reclassified
out of READ drops off the list by itself (tests pin both directions).

Request checks (`check_request`) are the defence against a web page or another local process using the server: the Host header must be the loopback
address and port the server is bound to (DNS rebinding), a browser Origin must be loopback, and the bearer token must match (constant time)."""
import hmac
import json

from . import tool_lists

SERVER_NAME = "cartogen-ai"
PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
MAX_BODY_BYTES = 1_000_000
MAX_RESULT_CHARS = 200_000

READ_TOOLS = tool_lists.READ_TOOLS
ALLOWED_TOOLS = READ_TOOLS          # the name MCP code and tests already use

WRITE_TOOLS = tool_lists.WRITE_TOOLS

INSTRUCTIONS = ("Cartogen AI's view of the open QGIS project. Layers marked RESTRICTED or SENSITIVE are never returned. Read tools run at once and never "
                "return feature values. Write tools wait for the user to approve each call in QGIS and are refused if the user says no or does not answer. "
                "Any other tool is refused; ask the user to do it in QGIS.")
APPROVAL_NOTE = " (runs only after the user approves this call in QGIS)"
MAX_APPROVAL_ARG_CHARS = 1500

# JSON-RPC error codes
PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS = -32700, -32600, -32601, -32602


def loopback_hosts(port):
    return {f"127.0.0.1:{port}", f"localhost:{port}"}


def check_request(headers, token, port):
    """(status, reason) for an HTTP request's headers: (200, '') when it may proceed, else the HTTP status to answer with. Pure.
    Order matters: the cheap structural checks first, the token last so a wrong Host never learns whether the token was right."""
    def get(key):
        return headers.get(key) or headers.get(key.lower()) or ""

    if get("Host") not in loopback_hosts(port):
        return 403, "Host not allowed"
    origin = get("Origin")
    if origin and origin not in {f"http://{h}" for h in loopback_hosts(port)}:       # only this server's own origin; a page on any other port is another program
        return 403, "Origin not allowed"
    auth = get("Authorization")
    scheme, _, given = auth.partition(" ")
    if scheme.lower() != "bearer" or not token or not hmac.compare_digest(given.strip().encode(), token.encode()):
        return 401, "Missing or wrong token"
    return 200, ""


def tool_descriptors(schemas, writes=False):
    """MCP tool descriptors for the allowed tools found in `schemas` (the OpenAI-style list the plugin keeps); the write tools too when `writes` (an
    approval function exists), each marked as needing approval. Sorted by name. Pure."""
    out = []
    for item in schemas:
        fn = item.get("function", {}) if isinstance(item, dict) else {}
        name = fn.get("name")
        if name in ALLOWED_TOOLS or (writes and name in WRITE_TOOLS):
            note = APPROVAL_NOTE if name in WRITE_TOOLS else ""
            out.append({"name": name, "description": fn.get("description", "") + note,
                        "inputSchema": fn.get("parameters") or {"type": "object", "properties": {}}})
    return sorted(out, key=lambda t: t["name"])


def approval_text(name, arguments, operation):
    """What the person sees when asked to approve a call: the tool, what kind of change it is, and the arguments exactly as sent (cut when long). Pure."""
    try:
        shown = json.dumps(arguments, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        shown = str(arguments)
    if len(shown) > MAX_APPROVAL_ARG_CHARS:
        shown = shown[:MAX_APPROVAL_ARG_CHARS] + f"\n... ({len(shown) - MAX_APPROVAL_ARG_CHARS} more characters not shown)"
    return (f"An outside AI program asks Cartogen AI to run:\n\n  {name}   [{operation}]\n\nwith these arguments:\n\n{shown}\n\n"
            "Allow this one call? Cartogen AI's Undo does not cover changes made this way. If you do not answer, the call is refused.")


def refusal(name, known, writes=False):
    """The result for a tool that may not be called over MCP. Nothing ran. Pure."""
    why = ("This tool is not available over MCP. Ask the user to do it in QGIS." if known else f"Unknown tool: {name}")
    if known and name in WRITE_TOOLS and not writes:
        why = "Changes are not enabled on this server: it is read-only. Ask the user to do it in QGIS."
    return {"status": "NOT_RUN", "error": why}


def _text_result(payload, is_error=False):
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(text) > MAX_RESULT_CHARS:
        text = json.dumps({"truncated": True, "note": f"The result was {len(text)} characters; the first {MAX_RESULT_CHARS} are shown.",
                           "text_start": text[:MAX_RESULT_CHARS]}, ensure_ascii=False)
    return {"content": [{"type": "text", "text": text}], "isError": bool(is_error)}


def _error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle(message, list_tools, call_tool, known_tools=frozenset(), writes=False):
    """The JSON-RPC reply (dict) to one parsed request, or None for a notification. `list_tools()` returns descriptors, `call_tool(name, args)` returns
    the tool's result dict (only ever called for an allowed tool). Pure given those two. Never raises."""
    try:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
            return _error(message.get("id") if isinstance(message, dict) else None, INVALID_REQUEST, "Not a JSON-RPC 2.0 request.")
        method, request_id, params = message["method"], message.get("id"), message.get("params") or {}
        if "id" not in message:
            return None                                  # a notification (for example notifications/initialized): no reply
        if method == "initialize":
            wanted = params.get("protocolVersion") if isinstance(params, dict) else None
            version = wanted if wanted in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
            return {"jsonrpc": "2.0", "id": request_id, "result": {
                "protocolVersion": version, "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": "1"}, "instructions": INSTRUCTIONS}}
        if method == "ping":
            return {"jsonrpc": "2.0", "id": request_id, "result": {}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": list_tools()}}
        if method == "tools/call":
            name, arguments = (params.get("name"), params.get("arguments") or {}) if isinstance(params, dict) else (None, {})
            if not isinstance(name, str) or not isinstance(arguments, dict):
                return _error(request_id, INVALID_PARAMS, "tools/call needs a tool name and an arguments object.")
            if name not in ALLOWED_TOOLS and not (writes and name in WRITE_TOOLS):
                return {"jsonrpc": "2.0", "id": request_id, "result": _text_result(refusal(name, name in known_tools, writes), True)}
            result = call_tool(name, arguments)
            failed = isinstance(result, dict) and ("error" in result or result.get("status") in ("EGRESS_BLOCKED", "PREVIEW_REQUIRED", "NOT_RUN", "DENIED"))
            return {"jsonrpc": "2.0", "id": request_id, "result": _text_result(result, failed)}
        return _error(request_id, METHOD_NOT_FOUND, f"Method not found: {method}")
    except Exception as e:                               # a bug here must not take the server down or leak a traceback
        return _error(message.get("id") if isinstance(message, dict) else None, -32603, f"Internal error ({type(e).__name__}).")
