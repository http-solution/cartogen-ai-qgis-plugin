"""PLAN-044: the source record on a real QGIS layer -- the orchestrator's tagging step, the provenance record and the markdown report.

Written without a QGIS install: CI's first run is its first execution."""
import json
import unittest

try:
    from qgis.core import QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestSourceRecordLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.layer = QgsVectorLayer("Point?crs=EPSG:4326&field=a:string", "Quakes", "memory")
        QgsProject.instance().addMapLayer(self.layer)

    def test_the_orchestrator_step_stores_the_record_on_the_named_layer(self):
        from cartogen_ai.core.agent import source_record
        from cartogen_ai.core.agent.agent_orchestrator import CartogenAi
        result = source_record.attach("fetch_usgs_earthquakes", {"days": 7}, {"success": True, "layer_name": "Quakes"})
        CartogenAi._tag_fetched_layer_source(result)
        stored = json.loads(self.layer.customProperty(source_record.PROPERTY_KEY))
        self.assertEqual(stored[0]["tool"], "fetch_usgs_earthquakes")
        self.assertEqual(stored[0]["coverage"], "last 7 days")

    def test_the_provenance_record_and_report_carry_it_and_a_derived_layer_inherits_it(self):
        from cartogen_ai.core.agent import provenance, source_record
        from cartogen_ai.core.agent.lineage import tag_layer_lineage
        from cartogen_ai.core.agent.tools import export_tools
        source_record.tag_layer(self.layer, source_record.build("fetch_usgs_earthquakes", {}, {"success": True}))
        derived = QgsVectorLayer("Point?crs=EPSG:4326&field=a:string", "Buffered", "memory")
        QgsProject.instance().addMapLayer(derived)
        tag_layer_lineage(derived, "buffer", {}, ["Quakes"])
        lookup = lambda name: next(iter(QgsProject.instance().mapLayersByName(name)), None)     # noqa: E731
        record = provenance.build_provenance_record(derived, lookup)
        self.assertEqual([r["tool"] for r in record["sources"]], ["fetch_usgs_earthquakes"])
        report = export_tools.generate_spatial_report("t", "x", ["Buffered"])["report"]
        self.assertIn("Data source:", report)
        self.assertIn("USGS Earthquake Hazards Program", report)


if __name__ == "__main__":
    unittest.main()
