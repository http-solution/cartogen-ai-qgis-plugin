"""PLAN-034: the MCP server's policy (pure) and its HTTP behaviour on the loopback address with a stub tool runner. No QGIS needed."""
import json
import unittest
import urllib.error
import urllib.request

from cartogen_ai.core import tool_operations
from cartogen_ai.core.agent import mcp_policy, mcp_server

GOOD = object()         # sentinel: "use the server's real token"
BAD = "x" * 8         # a wrong token
SCHEMAS = [{"type": "function", "function": {"name": n, "description": f"{n} doc", "parameters": {"type": "object", "properties": {"layer_name": {"type": "string"}}}}}
           for n in ("get_layers", "get_attributes", "buffer", "execute_pyqgis_script")]


class TestAllowlist(unittest.TestCase):
    def test_every_allowed_tool_exists_and_is_classified_read(self):
        from cartogen_ai.core.agent.tools.registry import TOOL_REGISTRY
        import cartogen_ai.core.agent.agent_orchestrator  # noqa: F401  (registers every tool)
        missing = sorted(t for t in mcp_policy.ALLOWED_TOOLS if t not in TOOL_REGISTRY)
        not_read = sorted(t for t in mcp_policy.ALLOWED_TOOLS if tool_operations.get_tool_operation_type(t) != tool_operations.READ)
        self.assertEqual((missing, not_read), ([], []))

    def test_dangerous_read_classified_tools_are_not_on_the_list(self):
        for name in ("run_steps", "gemini_grounded_search", "openai_grounded_search", "extract_pdf_tables", "extract_word_tables", "web_research",
                     "search_web", "geocode_batch", "execute_pyqgis_script", "set_map_view", "select_by_expression", "load_3w_data", "inspect_canvas_visually"):
            self.assertNotIn(name, mcp_policy.ALLOWED_TOOLS)

    def test_descriptors_only_list_allowed_tools_with_input_schemas(self):
        names = [t["name"] for t in mcp_policy.tool_descriptors(SCHEMAS)]
        self.assertEqual(names, ["get_attributes", "get_layers"])
        self.assertIn("properties", mcp_policy.tool_descriptors(SCHEMAS)[0]["inputSchema"])


class TestCheckRequest(unittest.TestCase):
    def ok(self, **over):
        h = {"Host": "127.0.0.1:5000", "Authorization": "Bearer secret"}
        h.update(over)
        return mcp_policy.check_request({k: v for k, v in h.items() if v is not None}, "secret", 5000)[0]

    def test_a_good_request_passes(self):
        self.assertEqual(self.ok(), 200)
        self.assertEqual(self.ok(Host="localhost:5000"), 200)

    def test_wrong_host_is_refused_before_the_token_is_looked_at(self):
        self.assertEqual(self.ok(Host="evil.example:5000"), 403)
        self.assertEqual(self.ok(Host="127.0.0.1:6000"), 403)
        self.assertEqual(self.ok(Host=None), 403)

    def test_a_foreign_browser_origin_is_refused(self):
        self.assertEqual(self.ok(Origin="https://evil.example"), 403)
        self.assertEqual(self.ok(Origin="http://127.0.0.1:8080"), 403)
        self.assertEqual(self.ok(Origin="http://127.0.0.1:5000"), 200)

    def test_missing_or_wrong_token(self):
        self.assertEqual(self.ok(Authorization=None), 401)
        self.assertEqual(self.ok(Authorization="Bearer nope"), 401)
        self.assertEqual(self.ok(Authorization="Basic secret"), 401)
        self.assertEqual(mcp_policy.check_request({"Host": "127.0.0.1:5000", "Authorization": "Bearer "}, "", 5000)[0], 401)


class TestHandle(unittest.TestCase):
    def handle(self, message, calls=None):
        def call(name, args):
            (calls if calls is not None else []).append((name, args))
            return {"success": True, "layers": []}
        return mcp_policy.handle(message, lambda: mcp_policy.tool_descriptors(SCHEMAS), call, known_tools={"buffer", "get_layers"})

    def test_initialize_negotiates_and_declares_only_tools(self):
        r = self.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}})["result"]
        self.assertEqual(r["protocolVersion"], "2025-03-26")
        self.assertEqual(list(r["capabilities"]), ["tools"])
        self.assertEqual(self.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "1999"}})["result"]["protocolVersion"],
                         mcp_policy.PROTOCOL_VERSIONS[0])

    def test_notifications_get_no_reply(self):
        self.assertIsNone(self.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_a_write_tool_is_refused_and_never_called(self):
        calls = []
        reply = self.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "buffer", "arguments": {"layer_name": "x"}}}, calls)
        self.assertEqual(calls, [])
        self.assertTrue(reply["result"]["isError"])
        self.assertIn("read-only", reply["result"]["content"][0]["text"])

    def test_an_unknown_tool_is_refused_and_never_called(self):
        calls = []
        reply = self.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "nope", "arguments": {}}}, calls)
        self.assertEqual(calls, [])
        self.assertIn("Unknown tool", reply["result"]["content"][0]["text"])

    def test_an_allowed_tool_is_called_with_its_arguments(self):
        calls = []
        reply = self.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "get_layers", "arguments": {}}}, calls)
        self.assertEqual(calls, [("get_layers", {})])
        self.assertFalse(reply["result"]["isError"])

    def test_blocked_results_are_marked_as_errors(self):
        reply = mcp_policy.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "get_attributes", "arguments": {}}},
                                  list, lambda n, a: {"status": "EGRESS_BLOCKED", "error": "protected"})
        self.assertTrue(reply["result"]["isError"])

    def test_bad_input_gets_errors_not_exceptions(self):
        self.assertEqual(self.handle([1])["error"]["code"], mcp_policy.INVALID_REQUEST)
        self.assertEqual(self.handle({"jsonrpc": "2.0", "id": 1, "method": "nope"})["error"]["code"], mcp_policy.METHOD_NOT_FOUND)
        self.assertEqual(self.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": 5}})["error"]["code"], mcp_policy.INVALID_PARAMS)

    def test_a_huge_result_is_cut(self):
        reply = mcp_policy.handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "get_layers", "arguments": {}}},
                                  list, lambda n, a: {"blob": "x" * (mcp_policy.MAX_RESULT_CHARS + 10)})
        self.assertIn("truncated", reply["result"]["content"][0]["text"])


class TestArguments(unittest.TestCase):
    def test_unadvertised_arguments_are_dropped(self):
        self.assertEqual(mcp_server._filter_arguments(SCHEMAS, "get_layers", {"layer_name": "a", "confirmed": True, "x": 1}), {"layer_name": "a"})
        self.assertEqual(mcp_server._filter_arguments(SCHEMAS, "nope", {"a": 1}), {})


class TestHttp(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.server = mcp_server.McpServer(lambda f, a: f(a), schemas=SCHEMAS, call_tool=lambda n, a: self.calls.append((n, a)) or {"success": True})
        self.server.start()
        self.addCleanup(self.server.stop)

    def post(self, body, token=GOOD, host=None, origin=None, path="/mcp", raw=None):
        headers = {"Content-Type": "application/json", "Host": host or f"127.0.0.1:{self.server.port}"}
        if token is GOOD:
            headers["Authorization"] = f"Bearer {self.server.token}"
        elif token:
            headers["Authorization"] = f"Bearer {token}"
        if origin:
            headers["Origin"] = origin
        data = raw if raw is not None else json.dumps(body).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{self.server.port}{path}", data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_binds_loopback_only_and_has_a_fresh_token(self):
        self.assertTrue(self.server.url.startswith("http://127.0.0.1:"))
        self.assertGreaterEqual(len(self.server.token), 32)
        other = mcp_server.McpServer(lambda f, a: f(a), schemas=SCHEMAS)
        other.start()
        self.addCleanup(other.stop)
        self.assertNotEqual(other.token, self.server.token)

    def test_no_token_wrong_token_wrong_host_wrong_origin(self):
        msg = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
        self.assertEqual(self.post(msg, token=None)[0], 401)
        self.assertEqual(self.post(msg, token=BAD)[0], 401)
        self.assertEqual(self.post(msg, host="evil.example")[0], 403)
        self.assertEqual(self.post(msg, origin="https://evil.example")[0], 403)
        self.assertEqual(self.post(msg, path="/other")[0], 404)
        self.assertEqual(self.calls, [])

    def test_list_call_and_refusal_over_http(self):
        status, body = self.post({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertEqual(status, 200)
        self.assertEqual([t["name"] for t in json.loads(body)["result"]["tools"]], ["get_attributes", "get_layers"])
        status, body = self.post({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "get_layers", "arguments": {}}})
        self.assertEqual(json.loads(body)["result"]["isError"], False)
        status, body = self.post({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "buffer", "arguments": {"layer_name": "x"}}})
        self.assertTrue(json.loads(body)["result"]["isError"])
        self.assertEqual([c[0] for c in self.calls], ["get_layers"])

    def test_notification_is_202_and_bad_bodies_are_rejected(self):
        self.assertEqual(self.post({"jsonrpc": "2.0", "method": "notifications/initialized"})[0], 202)
        self.assertEqual(self.post(None, raw=b"{not json")[0], 400)
        self.assertEqual(self.post(None, raw=b"")[0], 400)

    def test_get_is_not_supported(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.server.port}/mcp", headers={"Authorization": f"Bearer {self.server.token}"})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 405)

    def test_stop_closes_the_port_and_forgets_the_token(self):
        port = self.server.port
        self.server.stop()
        self.assertIsNone(self.server.token)
        self.assertFalse(self.server.running)
        with self.assertRaises(OSError):
            urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/mcp", data=b"{}", method="POST"), timeout=2)


if __name__ == "__main__":
    unittest.main()
