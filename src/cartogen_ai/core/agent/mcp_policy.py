"""What an outside AI client may do over MCP, and how a request is judged (PLAN-034, roadmap step F, first slice). Pure: no sockets, no QGIS.

First slice, honestly: READ ONLY. A client can look at the open project (layers, attributes, extents, metadata, QA status); it cannot create, change,
delete, export or send anything. A call to any other tool is refused and nothing runs. There is no approval path yet: the plan's "preview, then a
person confirms in QGIS" needs a confirmation dialog that has not been built, so it is the next slice and an owner decision (see the plan).

The tool list is an ALLOWLIST written out below, not "every READ tool". Of the 83 tools classified READ, many are not safe to hand to an outside
client: `run_steps` runs other tools, the grounded-search tools spend the user's API key, `extract_pdf_tables` and friends read files from disk,
`geocode_*` and `web_research` send text to outside services, and `select_*`/`set_map_view` change what the user sees. A tool that is reclassified
out of READ drops off the list by itself (tests pin both directions).

Request checks (`check_request`) are the defence against a web page or another local process using the server: the Host header must be the loopback
address and port the server is bound to (DNS rebinding), a browser Origin must be loopback, and the bearer token must match (constant time)."""
import hmac
import json

SERVER_NAME = "cartogen-ai"
PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
MAX_BODY_BYTES = 1_000_000
MAX_RESULT_CHARS = 200_000

ALLOWED_TOOLS = frozenset({
    "get_layers", "get_attributes", "get_crs", "get_feature_count", "get_layer_extent", "get_layer_metadata", "get_layer_sensitivity",
    "get_layer_confidence", "get_dataset_status", "get_provenance_record", "field_statistics", "list_layouts", "list_layout_items",
    "list_map_themes", "list_bookmarks", "list_relations", "verify_crs_compatibility", "find_broken_layers", "check_pcode_uniqueness",
    "check_pcode_hierarchy", "validate_schema", "list_schema_contracts", "measure_distance", "find_tools",
})

INSTRUCTIONS = ("Cartogen AI's read-only view of the open QGIS project. Layers marked RESTRICTED or SENSITIVE are never returned. "
                "Anything that would change the project is refused; ask the user to do it in QGIS.")

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


def tool_descriptors(schemas):
    """MCP tool descriptors for the allowed tools found in `schemas` (the OpenAI-style list the plugin keeps). Sorted by name. Pure."""
    out = []
    for item in schemas:
        fn = item.get("function", {}) if isinstance(item, dict) else {}
        if fn.get("name") in ALLOWED_TOOLS:
            out.append({"name": fn["name"], "description": fn.get("description", ""),
                        "inputSchema": fn.get("parameters") or {"type": "object", "properties": {}}})
    return sorted(out, key=lambda t: t["name"])


def refusal(name, known):
    """The result for a tool that may not be called over MCP. Nothing ran. Pure."""
    why = ("This tool is not available over MCP: this server is read-only. Ask the user to do it in QGIS." if known
           else f"Unknown tool: {name}")
    return {"status": "NOT_RUN", "error": why}


def _text_result(payload, is_error=False):
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(text) > MAX_RESULT_CHARS:
        text = json.dumps({"truncated": True, "note": f"The result was {len(text)} characters; the first {MAX_RESULT_CHARS} are shown.",
                           "text_start": text[:MAX_RESULT_CHARS]}, ensure_ascii=False)
    return {"content": [{"type": "text", "text": text}], "isError": bool(is_error)}


def _error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle(message, list_tools, call_tool, known_tools=frozenset()):
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
            if name not in ALLOWED_TOOLS:
                return {"jsonrpc": "2.0", "id": request_id, "result": _text_result(refusal(name, name in known_tools), True)}
            result = call_tool(name, arguments)
            failed = isinstance(result, dict) and ("error" in result or result.get("status") in ("EGRESS_BLOCKED", "PREVIEW_REQUIRED", "NOT_RUN"))
            return {"jsonrpc": "2.0", "id": request_id, "result": _text_result(result, failed)}
        return _error(request_id, METHOD_NOT_FOUND, f"Method not found: {method}")
    except Exception as e:                               # a bug here must not take the server down or leak a traceback
        return _error(message.get("id") if isinstance(message, dict) else None, -32603, f"Internal error ({type(e).__name__}).")
