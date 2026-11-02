"""A local MCP server over the read-only part of the tool registry (PLAN-034, roadmap step F, first slice). Policy and protocol are in mcp_policy.py;
this module is the socket and the QGIS side.

Properties, by construction:
  * Binds 127.0.0.1 only, on an ephemeral port unless one is given. Off until a person starts it from the plugin menu; never started by a setting, so a
    restart of QGIS always begins with it off. The token is random per start, held in memory only, never written to disk or logged.
  * Streamable HTTP, JSON replies only (no event stream, no GET): POST /mcp.
  * A tool runs on the QGIS main thread through the plugin's existing ToolDispatcher, never on the HTTP thread.
  * Every call goes through the egress gate in ENFORCE mode with the client counted as NON-local, whatever the user's own egress setting is: a layer
    tagged RESTRICTED or SENSITIVE (or derived from one) is refused, with no override path.
  * Arguments the tool does not advertise are dropped (this is what stops a client passing `confirmed`).
Not verified in a real client (Claude Desktop, Claude Code, Cursor): the protocol is implemented from the MCP specification text, not tested against them."""
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ..logger import log_event
from . import mcp_policy


def _filter_arguments(schemas, name, arguments):
    """Only the arguments the tool advertises. Pure."""
    for item in schemas:
        fn = item.get("function", {}) if isinstance(item, dict) else {}
        if fn.get("name") == name:
            props = (fn.get("parameters") or {}).get("properties", {})
            return {k: v for k, v in arguments.items() if k in props}
    return {}


def egress_refusal(name, arguments):
    """The EGRESS_BLOCKED result when the call would return protected layer data to this client, else None. MAIN THREAD. A gate that cannot decide
    refuses (a privacy gate that fails open is worse than one that over-blocks)."""
    from ...core.models import egress_gate
    try:
        from qgis.core import QgsProject
        from .protection import lookups
        project = QgsProject.instance()
        get_level, get_sources = lookups(list(project.mapLayers().values()))
        decision = egress_gate.evaluate(
            mode=egress_gate.MODE_ENFORCE, provider_is_local=False, tool_name=name, arguments=arguments,
            project_layer_names=[layer.name() for layer in project.mapLayers().values()], get_level=get_level, get_sources=get_sources,
            strict=egress_gate.read_strict(), visible_layer_names=None)
    except Exception:
        return egress_gate.check_failed_decision(name)
    if decision is not None and decision.get("action") == "block":
        return decision["result"]
    return None


def run_allowed_tool(name, arguments):
    """Runs one allowed tool with the gate in front. MAIN THREAD."""
    from .tools.registry import TOOL_REGISTRY, TOOLS_SCHEMA
    func = TOOL_REGISTRY.get(name)
    if func is None:
        return {"error": f"Unknown tool: {name}"}
    args = _filter_arguments(TOOLS_SCHEMA, name, arguments)
    blocked = egress_refusal(name, args)
    if blocked is not None:
        log_event("mcp_call", tag="MCP", tool=name, status="egress_blocked")
        return blocked
    try:
        result = func(**args)
    except TypeError as e:
        return {"error": f"Invalid arguments for {name}: {e}"}
    except Exception as e:
        return {"error": f"Tool {name} failed: {type(e).__name__}"}
    log_event("mcp_call", tag="MCP", tool=name, status="error" if isinstance(result, dict) and "error" in result else "ok")
    return result if result is not None else {"error": "The tool returned nothing."}


class McpServer:
    """Start/stop wrapper. `run_on_main(func, arg)` must run `func(arg)` on the QGIS main thread and return its result (the plugin passes the existing
    dispatcher; tests pass a direct call). `call_tool(name, args)` defaults to run_allowed_tool."""

    def __init__(self, run_on_main, schemas=None, call_tool=None, port=0):
        self._run_on_main = run_on_main
        self._call = call_tool or run_allowed_tool
        self._schemas = schemas
        self._port = port
        self._httpd = None
        self._thread = None
        self.token = None

    @property
    def running(self):
        return self._httpd is not None

    @property
    def port(self):
        return self._httpd.server_address[1] if self._httpd else None

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}/mcp" if self._httpd else None

    def start(self):
        if self._httpd is not None:
            return self.url
        self.token = secrets.token_urlsafe(32)
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            server_version = "CartogenMCP"

            def log_message(self, *args):           # the default writes request lines to stderr; the plugin logs metadata itself
                return

            def _send(self, status, body=b"", content_type="application/json"):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                if body:
                    self.wfile.write(body)

            def _json(self, status, payload):
                self._send(status, json.dumps(payload).encode())

            def do_GET(self):                       # no event stream in this slice
                self._send(405)

            def do_DELETE(self):
                self._send(405)

            def do_PUT(self):
                self._send(405)

            def do_PATCH(self):
                self._send(405)

            def do_POST(self):
                status, reason = mcp_policy.check_request(self.headers, server.token, server.port)
                if self.path.split("?", 1)[0] != "/mcp":
                    self._send(404)
                    return
                if status != 200:
                    log_event("mcp_request", tag="MCP", status="refused", http_status=status)
                    self._json(status, {"error": reason})
                    return
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    length = -1
                if length <= 0 or length > mcp_policy.MAX_BODY_BYTES:
                    self._json(413 if length > 0 else 400, {"error": "Body missing or too large"})
                    return
                try:
                    message = json.loads(self.rfile.read(length).decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    self._json(400, {"jsonrpc": "2.0", "id": None, "error": {"code": mcp_policy.PARSE_ERROR, "message": "Parse error"}})
                    return
                reply = mcp_policy.handle(message, server._list_tools, server._call_on_main, known_tools=server._known_tools())
                if reply is None:
                    self._send(202)
                else:
                    self._json(200, reply)

        self._httpd = ThreadingHTTPServer(("127.0.0.1", self._port), Handler)
        self._httpd.daemon_threads = True
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="cartogen-mcp", daemon=True)
        self._thread.start()
        log_event("mcp_server", tag="MCP", status="started")
        return self.url

    def stop(self):
        if self._httpd is None:
            return
        httpd, self._httpd = self._httpd, None
        httpd.shutdown()
        httpd.server_close()
        self.token = None
        log_event("mcp_server", tag="MCP", status="stopped")

    def _schema_list(self):
        if self._schemas is not None:
            return self._schemas
        from .tools.registry import TOOLS_SCHEMA
        return TOOLS_SCHEMA

    def _known_tools(self):
        return {item.get("function", {}).get("name") for item in self._schema_list() if isinstance(item, dict)}

    def _list_tools(self):
        return mcp_policy.tool_descriptors(self._schema_list())

    def _call_on_main(self, name, arguments):
        result = self._run_on_main(lambda _a: self._call(name, arguments), None)
        return result if result is not None else {"error": "The tool returned nothing."}
