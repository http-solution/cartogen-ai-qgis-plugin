"""The rc48 hand-test evidence (2026-10-23/24) reproduced as closely as CI allows: the REAL gpkg fixture layers, the REAL agent and its REAL
dispatch path (`_real_execute_tool`), not a hand-called helper. Two of the four evidence folders were explained from the code alone and the
explanation did not hold up against the folders themselves, so these print what actually happens and fail when the symptom is there.

OI-150  Cloud data protection = Block, smoke_points SENSITIVE (set the way the dialog sets it). Merging it must be gated (the run had no card at
        all), and the merge output must stay protected through two renames (the run read it with no card).
OI-128  yem_ppp_2020 (a copy of the DEM), vector layers above it as in the smoke project: apply_raster_stretch must leave a warm ramp that is
        still there after the layer is moved under the vectors, drawn on the canvas, and after a save and reload of the project.
Written without a QGIS install: CI's first run is its first execution."""
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from qgis.core import (QgsMapRendererSequentialJob, QgsMapSettings, QgsProject, QgsRasterLayer, QgsSettings,
                           QgsVectorLayer)
    from qgis.PyQt.QtCore import QSize
    from qgis.PyQt.QtGui import QColor
    LIVE = True
except ImportError:
    LIVE = False

INPUTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "release_smoke_assets", "inputs")
CLOUD = SimpleNamespace(base_url="https://generativelanguage.googleapis.com/v1beta")


def _boot():
    from tests.test_network_units_live import _boot as boot
    return boot()


def _add_gpkg(directory, layer, name=None):
    layer_obj = QgsVectorLayer(f"{os.path.join(directory, 'smoke_data.gpkg')}|layername={layer}", name or layer, "ogr")
    assert layer_obj.isValid(), layer
    QgsProject.instance().addMapLayer(layer_obj)
    return layer_obj


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestOi150RealFlow(unittest.TestCase):
    def setUp(self):
        from cartogen_ai.core.agent import agent_orchestrator as agent_mod
        from cartogen_ai.core.models import sensitivity
        from cartogen_ai.infrastructure.settings_keys import SETTINGS_EGRESS_GATE_MODE
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.workdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.workdir, True)
        shutil.copy(os.path.join(INPUTS, "smoke_data.gpkg"), self.workdir)
        settings = QgsSettings()
        previous = settings.value(SETTINGS_EGRESS_GATE_MODE, "off")
        settings.setValue(SETTINGS_EGRESS_GATE_MODE, "enforce")
        self.addCleanup(settings.setValue, SETTINGS_EGRESS_GATE_MODE, previous)
        self.points = _add_gpkg(self.workdir, "smoke_points")
        _add_gpkg(self.workdir, "smoke_hubs")
        self.assertTrue(sensitivity.set_layer_sensitivity(self.points, "SENSITIVE", "rc48 evidence"))
        self.agent = agent_mod.CartogenAi()
        self.agent.client = CLOUD

    def _run(self, tool, args, confirmed=False):
        result = self.agent._real_execute_tool(tool, args, user_confirmed=confirmed)
        print(f"EVIDENCE150 {tool} confirmed={confirmed} -> {str(result)[:260]}")
        return result

    def test_the_evidence_context_records_the_gate_state_and_each_layers_sensitivity(self):
        from cartogen_ai.core.agent import evidence
        context = evidence.project_context(CLOUD)
        print(f"EVIDENCE150 context egress {context.get('egress')}")
        self.assertEqual(context["egress"]["mode"], "enforce")
        self.assertFalse(context["egress"]["endpoint_is_local"])
        levels = {layer["name"]: layer["sensitivity"] for layer in context["layers"]}
        self.assertEqual(levels["smoke_points"], "SENSITIVE")
        self.assertIsNone(levels["smoke_hubs"])
        self.assertIn("persist_project_memory", context)

    def test_merging_the_sensitive_layer_is_gated_then_the_output_stays_protected(self):
        from cartogen_ai.core.agent.lineage import get_layer_lineage
        merge_args = {"layer_names_list": ["smoke_points", "smoke_hubs"]}
        first = self._run("merge_layers", merge_args)
        self.assertTrue(first.get("status") == "PREVIEW_REQUIRED" or first.get("blocked"),
                        f"merging a SENSITIVE layer with Cloud data protection = Block ran with no card: {first}")
        merged = self._run("merge_layers", merge_args, confirmed=True)
        self.assertTrue(merged.get("success"), merged)
        layer = QgsProject.instance().mapLayersByName(merged["layer_name"])[0]
        print(f"EVIDENCE150 lineage of {merged['layer_name']}: {get_layer_lineage(layer)}")
        self.assertTrue(get_layer_lineage(layer), "the merge output carries no lineage")
        self._run("rename_layer", {"old_name": merged["layer_name"], "new_name": "merged_test"}, confirmed=True)
        self._run("rename_layer", {"old_name": "merged_test", "new_name": "harmless_name"}, confirmed=True)
        for tool in ("get_attributes", "create_virtual_layer"):
            args = {"layer_name": "harmless_name"} if tool == "get_attributes" else {"sql": "SELECT * FROM harmless_name", "layer_name": "v"}
            decision = self.agent._egress_gate_decision(tool, args)
            print(f"EVIDENCE150 gate {tool} -> {decision and decision['action']}")
            self.assertIsNotNone(decision, f"{tool} on the renamed merge output was let through")
            self.assertEqual(decision["action"], "block")


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestOi128RealProject(unittest.TestCase):
    def setUp(self):
        from cartogen_ai.core.agent import agent_orchestrator as agent_mod
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.workdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.workdir, True)
        for name in ("smoke_data.gpkg", "smoke_dem.tif"):
            shutil.copy(os.path.join(INPUTS, name), self.workdir)
        dem_path = os.path.join(self.workdir, "smoke_dem.tif")
        self.dem = QgsRasterLayer(dem_path, "smoke_dem")
        self.ppp = QgsRasterLayer(dem_path, "yem_ppp_2020")          # "a second copy ... renamed to EXACTLY yem_ppp_2020"
        QgsProject.instance().addMapLayer(self.dem)
        QgsProject.instance().addMapLayer(self.ppp)
        for layer in ("smoke_boundary", "smoke_zones", "smoke_points", "smoke_hubs"):
            _add_gpkg(self.workdir, layer)                          # vector layers above the rasters, as in the smoke project
        self.agent = agent_mod.CartogenAi()

    def _canvas_colours(self):
        project = QgsProject.instance()
        layers = [n.layer() for n in project.layerTreeRoot().findLayers() if n.isVisible() and n.layer() is not None]
        order = [lyr for lyr in project.layerTreeRoot().layerOrder() if lyr in layers]
        settings = QgsMapSettings()
        settings.setLayers(order)
        settings.setExtent(self.ppp.extent())
        settings.setOutputSize(QSize(200, 200))
        settings.setBackgroundColor(QColor(255, 255, 255))
        job = QgsMapRendererSequentialJob(settings)
        job.start()
        job.waitForFinished()
        image = job.renderedImage()
        warm = grey = 0
        for y in range(0, 200, 4):
            for x in range(0, 200, 4):
                c = QColor(image.pixel(x, y))
                if c.red() - c.blue() >= 40:
                    warm += 1
                elif abs(c.red() - c.green()) < 12 and abs(c.green() - c.blue()) < 12 and c.red() != 255:
                    grey += 1
        return warm, grey

    def test_the_ramp_survives_the_move_under_the_vectors_the_canvas_and_a_save(self):
        result = self.agent._real_execute_tool("apply_raster_stretch", {"layer_name": "yem_ppp_2020", "mode": "color_ramp"})
        print(f"EVIDENCE128 tool result {result}")
        self.assertTrue(result.get("success"), result)
        layer = QgsProject.instance().mapLayersByName("yem_ppp_2020")[0]
        print(f"EVIDENCE128 renderer after the tool: {layer.renderer().type()}")
        self.assertEqual(layer.renderer().type(), "singlebandpseudocolor")
        tree = [n.name() for n in QgsProject.instance().layerTreeRoot().findLayers()]
        print(f"EVIDENCE128 layer order: {tree}")
        warm, grey = self._canvas_colours()
        print(f"EVIDENCE128 canvas sample: warm {warm}, grey {grey}")
        self.assertGreater(warm, grey, f"the canvas shows grey (warm {warm}, grey {grey}) although the ramp was applied")
        path = os.path.join(self.workdir, "saved.qgz")
        self.assertTrue(QgsProject.instance().write(path))
        reloaded = QgsProject()
        self.assertTrue(reloaded.read(path))
        again = reloaded.mapLayersByName("yem_ppp_2020")[0]
        print(f"EVIDENCE128 renderer after save and reload: {again.renderer().type()}")
        self.assertEqual(again.renderer().type(), "singlebandpseudocolor")


if __name__ == "__main__":
    unittest.main()
