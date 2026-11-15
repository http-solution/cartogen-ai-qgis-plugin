"""Live-QGIS run of every allow-listed Processing algorithm that has a row in tests/_processing_live_rows.py.
Written without a QGIS install: CI's first run is its first execution. A failure names the algorithm and the tool's own error."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False

from tests._processing_live_rows import LIVE_ROWS, SQUARE


def _add(kind, wkts, name):
    layer = QgsVectorLayer(f"{kind}?crs=EPSG:4326&field=name:string", name, "memory")
    feats = []
    for i, wkt in enumerate(wkts):
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(wkt))
        f.setAttributes([f"{name}{i}"])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    QgsProject.instance().addMapLayer(layer)


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestEveryAllowlistedAlgorithmRuns(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        _add("Point", ["POINT(0.2 0.2)", "POINT(0.8 0.2)", "POINT(0.2 0.8)", "POINT(1.6 1.6)"], "pts")
        _add("Point", ["POINT(0.5 0.5)"], "hub")
        _add("Polygon", [SQUARE, "POLYGON((1 0,2 0,2 1,1 1,1 0))"], "polys")
        _add("Polygon", ["POLYGON((0.5 0.2,1.5 0.2,1.5 0.8,0.5 0.8,0.5 0.2))"], "polys2")

    def test_each_row_runs_and_returns_a_layer(self):
        from cartogen_ai.core.agent.tools.processing_allowlist_tools import run_allowlisted_processing_algorithm
        failures = {}
        for alg_id, params in sorted(LIVE_ROWS.items()):
            res = run_allowlisted_processing_algorithm(alg_id, dict(params), new_layer_name="out_" + alg_id.split(":")[1])
            if not res.get("success"):
                failures[alg_id] = res.get("error", res)
        self.assertEqual(failures, {})


if __name__ == "__main__":
    unittest.main()
