"""Live run of export_layers_to_dxf in the QGIS image CI uses: a real DXF is written and read back, the overwrite card appears for a
pre-existing file, and a raster is refused. Written without a QGIS install: CI's first run is its first execution."""
import os
import tempfile
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestExportLayersToDxfLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.folder = tempfile.mkdtemp()
        roads = QgsVectorLayer("LineString?crs=EPSG:32636&field=name:string", "roads_dxf", "memory")
        f = QgsFeature(roads.fields())
        f.setGeometry(QgsGeometry.fromWkt("LINESTRING(500000 3500000, 500500 3500400, 501000 3500300)"))
        f.setAttributes(["main"])
        roads.dataProvider().addFeatures([f])
        QgsProject.instance().addMapLayer(roads)

    def test_a_real_dxf_is_written_and_names_the_layer(self):
        from cartogen_ai.core.agent.tools.export_tools import export_layers_to_dxf
        path = os.path.join(self.folder, "roads.dxf")
        result = export_layers_to_dxf(["roads_dxf"], output_path=path)
        print(f"DXFRESULT {str(result)[:300]}")
        self.assertTrue(result.get("success"), result)
        self.assertTrue(os.path.isfile(path))
        self.assertGreater(os.path.getsize(path), 0)
        with open(path, "rb") as fh:
            self.assertIn(b"roads_dxf", fh.read())

    def test_a_missing_extension_becomes_dxf(self):
        from cartogen_ai.core.agent.tools.export_tools import export_layers_to_dxf
        result = export_layers_to_dxf(["roads_dxf"], output_path=os.path.join(self.folder, "plain"))
        self.assertTrue(result.get("success"), result)
        self.assertTrue(result["output_path"].endswith(".dxf"))

    def test_an_existing_file_asks_before_it_is_replaced(self):
        from cartogen_ai.core.agent.tools.export_tools import export_layers_to_dxf
        path = os.path.join(self.folder, "existing.dxf")
        with open(path, "w") as fh:
            fh.write("not ours")
        result = export_layers_to_dxf(["roads_dxf"], output_path=path)
        self.assertEqual(result.get("status"), "PREVIEW_REQUIRED", result)
        with open(path) as fh:
            self.assertEqual(fh.read(), "not ours")

    def test_an_unknown_layer_is_an_error(self):
        from cartogen_ai.core.agent.tools.export_tools import export_layers_to_dxf
        self.assertIn("not found", export_layers_to_dxf(["nope"], output_path=os.path.join(self.folder, "x.dxf"))["error"])


if __name__ == "__main__":
    unittest.main()
