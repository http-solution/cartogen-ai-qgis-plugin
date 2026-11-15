"""PLAN-023 R9-5 on real QGIS layers: a point inside a polygon returns it with its attributes; the cell value of a raster read back equals the known cell; a CRS different from the
layer's is transformed; a point layer needs a radius; more than 50 matches are capped and say so; layers can be named; hidden layers are skipped by default. Written without a QGIS
install: CI's first run is its first execution."""
import os
import tempfile
import unittest

try:
    from osgeo import gdal
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsRasterLayer, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestIdentifyLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        from qgis.core import QgsCoordinateReferenceSystem
        QgsProject.instance().setCrs(QgsCoordinateReferenceSystem("EPSG:32636"))

    def _vector(self, spec, name, wkts, crs="EPSG:32636"):
        layer = QgsVectorLayer(f"{spec}?crs={crs}&field=name:string&field=pop:integer", name, "memory")
        feats = []
        for i, wkt in enumerate(wkts):
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(wkt))
            f.setAttributes([f"{name}{i}", i * 10])
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(layer)
        return layer

    def _call(self, **kw):
        from cartogen_ai.core.agent.tools.identify_tool import identify_at_point
        return identify_at_point(**kw)

    def test_a_point_inside_a_polygon_returns_it_with_its_attributes(self):
        self._vector("Polygon", "sq", ["POLYGON((0 0,10 0,10 10,0 10,0 0))", "POLYGON((20 20,30 20,30 30,20 30,20 20))"])
        out = self._call(x=5.0, y=5.0)
        self.assertTrue(out.get("success"), out)
        self.assertEqual(out["features_returned"], 1)
        row = out["vector_layers"][0]["features"][0]
        self.assertEqual(row["attributes"], {"name": "sq0", "pop": 0})

    def test_a_point_layer_needs_a_radius(self):
        self._vector("Point", "pts", ["POINT(5 5)"])
        miss = self._call(x=5.2, y=5.0)
        self.assertEqual(miss["features_returned"], 0)
        self.assertIn("radius", miss["hint"])
        hit = self._call(x=5.2, y=5.0, radius=0.5)
        self.assertEqual(hit["features_returned"], 1)

    def test_the_raster_cell_read_back_equals_the_known_cell(self):
        path = os.path.join(tempfile.mkdtemp(prefix="cartogen_id_"), "r.tif")
        import numpy as np
        arr = np.arange(16, dtype=np.float32).reshape(4, 4)
        ds = gdal.GetDriverByName("GTiff").Create(path, 4, 4, 1, gdal.GDT_Float32)
        ds.SetGeoTransform((500000.0, 10.0, 0.0, 4000040.0, 0.0, -10.0))
        from osgeo import osr
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(32636)
        ds.SetProjection(srs.ExportToWkt())
        ds.GetRasterBand(1).WriteArray(arr)
        ds = None
        layer = QgsRasterLayer(path, "rst")
        self.assertTrue(layer.isValid())
        QgsProject.instance().addMapLayer(layer)
        out = self._call(x=500025.0, y=4000015.0)                          # row 2, column 2 -> 10
        values = out["raster_layers"][0]["cell_values"]
        self.assertEqual(list(values.values()), [10.0])
        outside = self._call(x=1.0, y=1.0)
        self.assertIsNone(outside["raster_layers"][0]["cell_values"])

    def test_a_different_crs_is_transformed_to_the_layer(self):
        self._vector("Polygon", "geo", ["POLYGON((32.9 -0.1,33.1 -0.1,33.1 0.1,32.9 0.1,32.9 -0.1))"], crs="EPSG:4326")
        out = self._call(x=33.0, y=0.0, crs="EPSG:4326")
        self.assertEqual(out["features_returned"], 1)

    def test_more_than_fifty_matches_are_capped_and_say_so(self):
        self._vector("Polygon", "many", ["POLYGON((0 0,10 0,10 10,0 10,0 0))"] * 60)
        out = self._call(x=5.0, y=5.0)
        self.assertEqual(out["features_returned"], 50)
        self.assertTrue(out["truncated"])
        self.assertIn("50", out["note_truncated"])

    def test_layers_can_be_named_and_a_missing_name_is_an_error(self):
        self._vector("Polygon", "a", ["POLYGON((0 0,10 0,10 10,0 10,0 0))"])
        self._vector("Polygon", "b", ["POLYGON((0 0,10 0,10 10,0 10,0 0))"])
        out = self._call(x=5.0, y=5.0, layers=["b"])
        self.assertEqual([v["layer"] for v in out["vector_layers"]], ["b"])
        self.assertIn("not found", self._call(x=5.0, y=5.0, layers=["zzz"])["error"])

    def test_a_hidden_layer_is_skipped_by_default(self):
        layer = self._vector("Polygon", "hid", ["POLYGON((0 0,10 0,10 10,0 10,0 0))"])
        QgsProject.instance().layerTreeRoot().findLayer(layer.id()).setItemVisibilityChecked(False)
        self.assertEqual(self._call(x=5.0, y=5.0)["features_returned"], 0)
        self.assertEqual(self._call(x=5.0, y=5.0, layers=["hid"])["features_returned"], 1)

    def test_a_radius_of_a_degree_or_more_on_a_geographic_crs_is_refused(self):
        self.assertIn("degrees", self._call(x=33.0, y=0.0, crs="EPSG:4326", radius=5)["error"])


if __name__ == "__main__":
    unittest.main()
