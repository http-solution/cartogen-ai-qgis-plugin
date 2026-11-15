"""PLAN-021 WP-F, real QGIS (CI live job; written without a QGIS install, so CI's first run is its first execution): what a hand test could only
look at once is checked on every push.

- #97   twenty exchanges survive save and reopen, the export holds all forty with their times, and the Memory dialog's delete empties it.
- #120  a point layer a tool adds is kept with a saved project (and is still there after reopen), or the result says it is temporary.
- A18   a buffer of a SENSITIVE layer, renamed, is still protected: the lineage the agent records for the real tool survives the rename.
- A3    the sector coverage chart is a real picture, not a blank one."""
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from tests.test_network_units_live import QGIS_LIVE_AVAILABLE, _boot

if QGIS_LIVE_AVAILABLE:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsSettings, QgsVectorLayer


def _turn(n):
    return [{"role": "user", "content": f"Name layer number {n}"}, {"role": "assistant", "content": f"Layer {n} named"}]


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core bindings")
class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        why = _boot()
        if why:
            raise unittest.SkipTest(why)

    def setUp(self):
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)


class TestTwentyExchangesSurviveReopen(_Base):
    def setUp(self):
        super().setUp()
        from cartogen_ai.core.agent import chat_persistence as cp
        self.cp = cp
        QgsSettings().remove(cp.PERSIST_SETTING_KEY)
        self.addCleanup(lambda: QgsSettings().remove(cp.PERSIST_SETTING_KEY))

    def _export(self):
        from cartogen_ai.core.agent.tools import data_export_tools as det
        manager = MagicMock()
        manager.get_project_notes.return_value = {}
        manager.get_global_notes.return_value = {}
        path = os.path.join(self.tmp.name, "export.json")
        with patch.object(det, "get_memory_manager", return_value=manager):
            res = det.export_stored_data(path)
        self.assertTrue(res.get("success"), res)
        with open(path, encoding="utf-8") as handle:
            return res, json.load(handle)

    def test_all_forty_messages_are_in_the_export_after_save_and_reopen_and_the_delete_empties_it(self):
        history = []
        for n in range(1, 21):
            history += _turn(n)
            self.assertTrue(self.cp.save_chat_transcript(history[-10:], user_ts=f"2026-10-25T10:{n:02d}:00"))   # the agent only holds a short window
        project_file = os.path.join(self.tmp.name, "oi97_chat.qgz")
        self.assertTrue(QgsProject.instance().write(project_file))
        QgsProject.instance().clear()
        self.assertTrue(QgsProject.instance().read(project_file))
        res, doc = self._export()
        self.assertEqual(res["chat_history_count"], 40)
        messages = doc["chat_history"]
        self.assertEqual(messages[0]["content"], "Name layer number 1")
        self.assertEqual(messages[-1]["content"], "Layer 20 named")
        self.assertTrue(all(m.get("ts") for m in messages), "a message has no time")
        self.assertEqual(doc["chat_history_info"].get("transcript_dropped"), 0)
        removed = self.cp.clear_saved_chat_history()
        self.assertTrue(removed["success"])
        self.assertEqual(removed["removed"], 40)
        res2, _doc2 = self._export()
        self.assertEqual(res2["chat_history_count"], 0)


class TestPointLayerIsKeptOrSaidTemporary(_Base):
    POINTS = ({"name": "Origin", "lat": 15.3694, "lon": 44.191},)

    def test_in_a_saved_project_the_layer_is_kept_and_is_there_after_reopen(self):
        from cartogen_ai.core.agent.tools.humanitarian_tools import add_point_layer
        project_file = os.path.join(self.tmp.name, "p.qgz")
        self.assertTrue(QgsProject.instance().write(project_file))
        res = add_point_layer("Origin Point", list(self.POINTS), crs="EPSG:4326", crs_stated_by_user=True)
        self.assertTrue(res.get("success"), res)
        self.assertTrue(res.get("saved_with_project"), res)
        self.assertNotIn("temporary_note", res)
        layer = QgsProject.instance().mapLayersByName("Origin Point")[0]
        self.assertNotEqual(layer.providerType(), "memory")
        self.assertTrue(QgsProject.instance().write(project_file))
        QgsProject.instance().clear()
        self.assertTrue(QgsProject.instance().read(project_file))
        again = QgsProject.instance().mapLayersByName("Origin Point")[0]
        self.assertTrue(again.isValid())
        self.assertEqual(again.featureCount(), 1)

    def test_in_an_unsaved_project_the_result_says_it_is_temporary(self):
        from cartogen_ai.core.agent.tools.humanitarian_tools import add_point_layer
        res = add_point_layer("Origin Point", list(self.POINTS), crs="EPSG:4326", crs_stated_by_user=True)
        self.assertTrue(res.get("success"), res)
        self.assertTrue(res.get("temporary"), res)
        self.assertIn("temporary", res["temporary_note"])
        self.assertIn("has not been saved", res["temporary_note"])

    def test_a_second_point_added_to_the_kept_layer_works(self):
        from cartogen_ai.core.agent.tools.humanitarian_tools import add_point_layer
        QgsProject.instance().write(os.path.join(self.tmp.name, "p2.qgz"))
        add_point_layer("Origin Point", list(self.POINTS), crs="EPSG:4326", crs_stated_by_user=True)
        res = add_point_layer("Origin Point", [{"name": "Second", "lat": 15.40, "lon": 44.20}], crs="EPSG:4326", crs_stated_by_user=True)
        self.assertTrue(res.get("success"), res)
        self.assertEqual(QgsProject.instance().mapLayersByName("Origin Point")[0].featureCount(), 2)


class TestBufferThenRenameStaysProtected(_Base):
    def test_the_lineage_recorded_for_the_real_buffer_tool_survives_the_rename(self):
        from cartogen_ai.core.agent.agent_orchestrator import CartogenAi
        from cartogen_ai.core.agent.protection import effective_sensitivity, sensitivity_label
        from cartogen_ai.core.agent.tools.vector_tools import buffer_analysis
        from cartogen_ai.core.models.sensitivity import set_layer_sensitivity
        towns = QgsVectorLayer("Point?crs=EPSG:32638&field=name:string", "towns", "memory")
        f = QgsFeature(towns.fields())
        f.setGeometry(QgsGeometry.fromWkt("POINT(500000 1700000)"))
        f.setAttributes(["a"])
        towns.dataProvider().addFeatures([f])
        QgsProject.instance().addMapLayer(towns)
        set_layer_sensitivity(towns, "SENSITIVE", "test")
        before = set(QgsProject.instance().mapLayers())
        args = {"layer_name": "towns", "distance": 1000, "output_name": "towns_buf"}
        res = buffer_analysis(**args)
        self.assertTrue(res.get("success"), res)
        CartogenAi._tag_created_layers(None, "buffer_analysis", args, res, before)        # the step the agent runs after every tool call
        buf = QgsProject.instance().mapLayersByName("towns_buf")[0]
        buf.setName("harmless_buf")
        towns.setName("towns_renamed")
        record = effective_sensitivity(buf, list(QgsProject.instance().mapLayers().values()))
        self.assertEqual(record["level"], "SENSITIVE", record)
        self.assertIn("protected through lineage from 'towns_renamed'", sensitivity_label(record["level"], None, record["derived_from"]))
        from cartogen_ai.core.agent.tools.layout_item_tools import export_layout
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        QgsProject.instance().layerTreeRoot().findLayer(towns.id()).setItemVisibilityChecked(False)
        made = create_print_layout("Lineage Test", confirmed=True)
        self.assertTrue(made.get("success"), made)
        card = export_layout(made["layout_name"], os.path.join(self.tmp.name, "a.pdf"))
        self.assertEqual(card.get("status"), "PREVIEW_REQUIRED", card)
        self.assertIn("harmless_buf", json.dumps(card))
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "a.pdf")))


class TestCoverageChartIsDrawn(_Base):
    def test_the_chart_file_is_a_real_picture_with_ink_on_it(self):
        try:
            import matplotlib  # noqa: F401
        except ImportError:
            self.skipTest("matplotlib is not installed here")
        from qgis.PyQt.QtGui import QImage
        from cartogen_ai.core.agent.tools.reporting_tools import generate_sector_coverage_report
        rows = [{"sector": "Health", "reached": 900, "target": 1000}, {"sector": "WASH", "reached": 150, "target": 0},
                {"sector": "Shelter", "reached": 400, "target": 800}]
        res = generate_sector_coverage_report(rows, "sector", "reached", target_field="target", output_path=os.path.join(self.tmp.name, "c.png"))
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["no_target_groups"], ["WASH"])
        image = QImage(res["chart_path"])
        self.assertFalse(image.isNull())
        dark = sum(1 for x in range(0, image.width(), 6) for y in range(0, image.height(), 6) if (image.pixelColor(x, y).lightness() < 235))
        self.assertGreater(dark, 200, "the chart image is blank")


if __name__ == "__main__":
    unittest.main()
