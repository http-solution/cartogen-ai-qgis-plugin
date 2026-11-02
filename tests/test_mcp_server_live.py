"""PLAN-034: the MCP server on a real QGIS project -- the tool really runs on the main thread, a protected layer is refused whatever the user's own
egress setting is, and a write tool is refused without changing anything.

Written without a QGIS install: CI's first run is its first execution."""
import json
import threading
import time
import unittest
import urllib.request

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsSettings, QgsVectorLayer
    from qgis.PyQt.QtCore import QCoreApplication
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestMcpServerLive(unittest.TestCase):
    def setUp(self):
        from cartogen_ai.core.agent.mcp_server import McpServer
        from cartogen_ai.core.agent.tool_dispatcher import ToolDispatcher
        from cartogen_ai.core.models import sensitivity
        from cartogen_ai.infrastructure.settings_keys import SETTINGS_EGRESS_GATE_MODE
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        settings = QgsSettings()
        previous = settings.value(SETTINGS_EGRESS_GATE_MODE, "off")
        settings.setValue(SETTINGS_EGRESS_GATE_MODE, "off")          # the user's own gate is OFF: the MCP gate must not depend on it
        self.addCleanup(settings.setValue, SETTINGS_EGRESS_GATE_MODE, previous)
        self.open_layer = self._points("open_pts")
        self.secret_layer = self._points("secret_pts")
        sensitivity.set_layer_sensitivity(self.secret_layer, "SENSITIVE", "test")
        self.dispatcher = ToolDispatcher(None)

        def run_on_main(func, arg):
            result = []
            self.dispatcher.request_callable.emit(func, arg, result)
            return result[0] if result else None

        self.server = McpServer(run_on_main)
        self.server.start()
        self.addCleanup(self.server.stop)

    def _points(self, name):
        layer = QgsVectorLayer("Point?crs=EPSG:4326&field=who:string", name, "memory")
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(1, 1)))
        feature.setAttributes(["alice"])
        layer.dataProvider().addFeatures([feature])
        QgsProject.instance().addMapLayer(layer)
        return layer

    def _rpc(self, payload):
        """POSTs from a worker thread while this (main) thread keeps the Qt event loop running, as QGIS does."""
        out = {}

        def work():
            req = urllib.request.Request(self.server.url, data=json.dumps(payload).encode(), method="POST", headers={
                "Content-Type": "application/json", "Authorization": f"Bearer {self.server.token}", "Host": f"127.0.0.1:{self.server.port}"})
            try:
                with urllib.request.urlopen(req, timeout=20) as r:
                    out["body"] = json.loads(r.read())
            except Exception as e:                   # surfaced by the assertion below
                out["error"] = repr(e)

        thread = threading.Thread(target=work)
        thread.start()
        deadline = time.monotonic() + 25
        while thread.is_alive() and time.monotonic() < deadline:
            QCoreApplication.processEvents()
            time.sleep(0.01)
        self.assertNotIn("error", out, out)
        return out["body"]

    def _call(self, name, arguments):
        body = self._rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}})
        return body["result"]["isError"], json.loads(body["result"]["content"][0]["text"])

    def test_an_open_layer_is_read_on_the_main_thread(self):
        is_error, payload = self._call("get_attributes", {"layer_name": "open_pts"})
        self.assertFalse(is_error, payload)
        self.assertIn("alice", json.dumps(payload))

    def test_a_sensitive_layer_is_refused_even_with_the_users_gate_off(self):
        is_error, payload = self._call("get_attributes", {"layer_name": "secret_pts"})
        self.assertTrue(is_error)
        self.assertNotIn("alice", json.dumps(payload))

    def test_a_write_tool_is_refused_and_the_project_is_unchanged(self):
        before = sorted(layer.name() for layer in QgsProject.instance().mapLayers().values())
        is_error, payload = self._call("buffer", {"layer_name": "open_pts", "distance": 1})
        self.assertTrue(is_error)
        self.assertEqual(payload.get("status"), "NOT_RUN")
        self.assertEqual(sorted(layer.name() for layer in QgsProject.instance().mapLayers().values()), before)

    def test_the_tool_list_has_only_allowed_tools(self):
        from cartogen_ai.core.agent import mcp_policy
        body = self._rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = {t["name"] for t in body["result"]["tools"]}
        self.assertTrue(names)
        self.assertLessEqual(names, mcp_policy.ALLOWED_TOOLS)


if __name__ == "__main__":
    unittest.main()
