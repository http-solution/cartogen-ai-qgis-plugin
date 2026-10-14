"""Live-QGIS tests for create_empty_layer, add_basemap and add_web_layer and the new sublayer option of add_layer_from_path.
Written without a QGIS install: CI's first run is their first execution. Nothing here needs the network: a basemap/web layer is only
checked for being constructed and added (QGIS accepts the source string; a tile that never loads does not make the layer invalid)."""
import os
import tempfile
import unittest

try:
    from qgis.core import QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestDataSourceToolsLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def test_an_empty_scratch_polygon_layer_with_fields(self):
        from cartogen_ai.core.agent.tools.data_source_tools import create_empty_layer
        res = create_empty_layer("parcels", "polygon", [{"name": "name", "type": "string"}, {"name": "pop", "type": "integer"}])
        self.assertTrue(res.get("success"), res)
        layer = QgsProject.instance().mapLayersByName("parcels")[0]
        self.assertEqual([f.name() for f in layer.fields()], ["name", "pop"])
        self.assertEqual(layer.featureCount(), 0)
        self.assertEqual(layer.geometryType(), 2)   # polygon

    def test_a_table_without_geometry(self):
        from cartogen_ai.core.agent.tools.data_source_tools import create_empty_layer
        res = create_empty_layer("notes", "none", [{"name": "text", "type": "string"}])
        self.assertTrue(res.get("success"), res)
        self.assertEqual(QgsProject.instance().mapLayersByName("notes")[0].featureCount(), 0)

    def test_a_geopackage_is_created_and_reopened(self):
        from cartogen_ai.core.agent.tools.data_source_tools import create_empty_layer
        path = os.path.join(tempfile.mkdtemp(), "sites.gpkg")
        res = create_empty_layer("sites", "point", [{"name": "code", "type": "string"}], file_path=path, confirmed=True)
        self.assertTrue(res.get("success"), res)
        self.assertTrue(os.path.exists(path))
        self.assertEqual([f.name() for f in QgsProject.instance().mapLayersByName("sites")[0].fields()][-1], "code")

    def test_bad_input_is_refused_not_raised(self):
        from cartogen_ai.core.agent.tools.data_source_tools import create_empty_layer
        self.assertIn("error", create_empty_layer("x", "blob"))
        self.assertIn("error", create_empty_layer("x", "point", [{"name": "a&b"}]))
        self.assertIn("error", create_empty_layer("x", "point", file_path="/tmp/x.txt"))

    def test_basemap_goes_to_the_bottom_and_is_not_duplicated(self):
        from cartogen_ai.core.agent.tools.data_source_tools import add_basemap, create_empty_layer
        create_empty_layer("above", "point")
        res = add_basemap("osm")
        self.assertTrue(res.get("success"), res)
        order = [n.name() for n in QgsProject.instance().layerTreeRoot().children()]
        self.assertEqual(order[-1], "OpenStreetMap")
        again = add_basemap("openstreetmap")
        self.assertTrue(again.get("reused_existing_layer"), again)
        self.assertEqual(len(QgsProject.instance().mapLayersByName("OpenStreetMap")), 1)

    def test_web_layer_sources_are_accepted_by_qgis(self):
        from cartogen_ai.core.agent.tools.data_source_tools import add_web_layer
        res = add_web_layer("xyz", "https://tile.openstreetmap.org/{z}/{x}/{y}.png", layer_name="tiles")
        self.assertTrue(res.get("success"), res)

    def test_a_private_address_is_refused_before_qgis_sees_it(self):
        from cartogen_ai.core.agent.tools.data_source_tools import add_web_layer
        self.assertIn("error", add_web_layer("wms", "https://192.168.0.1/wms", layer="a"))

    def test_sublayer_picks_one_table_of_a_multi_layer_geopackage(self):
        from qgis.core import QgsFeature, QgsGeometry, QgsVectorFileWriter
        from cartogen_ai.core.agent.tools.vector_tools import add_layer_from_path
        path = os.path.join(tempfile.mkdtemp(), "two.gpkg")
        for index, name in enumerate(("alpha", "beta")):
            src = QgsVectorLayer("Point?crs=EPSG:4326&field=n:string", name, "memory")
            feat = QgsFeature(src.fields())
            feat.setGeometry(QgsGeometry.fromWkt("POINT(1 1)"))
            src.dataProvider().addFeatures([feat])
            opts = QgsVectorFileWriter.SaveVectorOptions()
            opts.driverName = "GPKG"
            opts.layerName = name
            opts.actionOnExistingFile = (QgsVectorFileWriter.CreateOrOverwriteFile if index == 0
                                         else QgsVectorFileWriter.CreateOrOverwriteLayer)
            QgsVectorFileWriter.writeAsVectorFormatV3(src, path, QgsProject.instance().transformContext(), opts)
        first = add_layer_from_path(path)
        self.assertTrue(first.get("success"), first)
        self.assertIn("beta", first.get("sublayer_note", ""))
        QgsProject.instance().clear()
        chosen = add_layer_from_path(path, layer_name="picked", sublayer="beta")
        self.assertTrue(chosen.get("success"), chosen)
        self.assertEqual(QgsProject.instance().mapLayersByName("picked")[0].source().split("layername=")[-1], "beta")


if __name__ == "__main__":
    unittest.main()
