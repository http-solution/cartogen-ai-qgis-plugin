# -*- coding: utf-8 -*-
"""Live check that a tool returning a LIST reaches the model as that list, through the real CartogenAi._execute_tool path.

rc15 hand test (2026-10-06): get_layers and get_attributes both came back as "Execution failed unexpectedly." because the #138
main-thread wrapper kept only dict results. The offline test (test_project_session.py) uses a fake dispatcher; this one runs the
real tool against a real QgsProject. Needs real qgis.core bindings and skips itself without them. Not in the sandbox: it runs in
the `qgis-live-tests` CI job (tests/_ci_run_live_tests.py)."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from qgis.core import QgsProject, QgsVectorLayer
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


def _boot_qgis():
    # The ONE QgsApplication the whole live job shares (tests/test_chat_widget_live.py). A second QgsApplication created here
    # let every test pass and then crashed the interpreter at exit (CI, 2026-10-06: "Ran 287 tests ... OK", then
    # "Segmentation fault (core dumped)" with no crash in the control process).
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core bindings")
class TestListResultsReachTheModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _boot_qgis()
        import cartogen_ai.core.agent.agent_orchestrator as agent_mod
        cls.agent_mod = agent_mod

    def setUp(self):
        QgsProject.instance().clear()
        layer = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string", "Points", "memory")
        QgsProject.instance().addMapLayer(layer)

    def test_get_layers_is_not_reported_as_a_failure(self):
        agent = self.agent_mod.CartogenAi()
        res = agent._execute_tool("get_layers", "{}")
        self.assertIsInstance(res, list, res)
        self.assertEqual([e["name"] for e in res], ["Points"])

    def test_get_attributes_is_not_reported_as_a_failure(self):
        agent = self.agent_mod.CartogenAi()
        res = agent._execute_tool("get_attributes", '{"layer_name": "Points"}')
        self.assertNotEqual(res, {"error": "Execution failed unexpectedly."})
