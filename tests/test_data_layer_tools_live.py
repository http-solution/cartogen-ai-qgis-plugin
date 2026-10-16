"""Live-QGIS tests for package C (data_layer_tools.py and the new file types of add_layer_from_path). Written without a QGIS install:
CI's first run is their first execution. The PostGIS test needs the live job's postgis service (CARTOGEN_TEST_PG_HOST)."""
import os
import tempfile
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsMeshLayer, QgsProject, QgsRasterLayer, QgsSettings, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


def _points(name, rows):
    layer = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string&field=pop:integer", name, "memory")
    for i, (n, pop) in enumerate(rows):
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(f"POINT({i} {i})"))
        f.setAttributes([n, pop])
        layer.dataProvider().addFeatures([f])
    return layer


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestDataLayerToolsLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.tmp = tempfile.mkdtemp()
        self.towns = _points("towns", (("a", 5), ("b", 50), ("c", 500)))
        QgsProject.instance().addMapLayer(self.towns)

    def test_virtual_layer_runs_a_select_over_a_project_layer(self):
        from cartogen_ai.core.agent.tools.data_layer_tools import create_virtual_layer
        res = create_virtual_layer("big_towns", "SELECT name, pop, geometry FROM towns WHERE pop > 10")
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["feature_count"], 2)
        self.assertTrue(res["geometry"])
        self.assertTrue(QgsProject.instance().mapLayersByName("big_towns")[0].isValid())

    def test_virtual_layer_refuses_unsafe_or_broken_sql(self):
        from cartogen_ai.core.agent.tools.data_layer_tools import create_virtual_layer
        self.assertIn("error", create_virtual_layer("x", "DROP TABLE towns"))
        self.assertIn("error", create_virtual_layer("x", "SELECT * FROM \"ogr:/etc/passwd\""))
        self.assertIn("error", create_virtual_layer("x", "SELECT * FROM no_such_layer"))
        self.assertIn("already exists", create_virtual_layer("towns", "SELECT * FROM towns")["error"])
        self.assertFalse(QgsProject.instance().mapLayersByName("x"))

    def test_qlr_round_trip_keeps_the_layer_and_refuses_overwrite_without_confirmation(self):
        from cartogen_ai.core.agent.tools.data_layer_tools import load_layer_definition, save_layer_definition
        path = os.path.join(self.tmp, "towns.qlr")
        res = save_layer_definition(["towns"], path)
        self.assertTrue(res.get("success"), res)
        self.assertTrue(os.path.getsize(path) > 0)
        # a file this plugin did not write is not replaced silently
        other = os.path.join(self.tmp, "other.qlr")
        with open(other, "w") as fh:
            fh.write("not mine")
        self.assertEqual(save_layer_definition(["towns"], other)["status"], "PREVIEW_REQUIRED")
        self.assertIn("error", save_layer_definition(["nope"], os.path.join(self.tmp, "n.qlr")))
        before = set(QgsProject.instance().mapLayers())
        loaded = load_layer_definition(path)
        self.assertTrue(loaded.get("success"), loaded)
        self.assertEqual(loaded["layers_added"], ["towns"])
        self.assertEqual(len(set(QgsProject.instance().mapLayers()) - before), 1)

    def test_load_layer_definition_rejects_bad_paths(self):
        from cartogen_ai.core.agent.tools.data_layer_tools import load_layer_definition
        self.assertIn("error", load_layer_definition(os.path.join(self.tmp, "missing.qlr")))
        self.assertIn("error", load_layer_definition(os.path.join(self.tmp, "x.qml")))

    def test_package_layers_offline(self):
        from cartogen_ai.core.agent.tools.data_layer_tools import package_layers_offline
        path = os.path.join(self.tmp, "pack.gpkg")
        res = package_layers_offline(["towns"], path)
        self.assertTrue(res.get("success"), res)
        packed = QgsVectorLayer(f"{path}|layername=towns", "check", "ogr")
        self.assertTrue(packed.isValid())
        self.assertEqual(packed.featureCount(), 3)
        self.assertIn("error", package_layers_offline(["towns"], os.path.join(self.tmp, "p.shp")))
        self.assertIn("error", package_layers_offline(["nope"], os.path.join(self.tmp, "q.gpkg")))

    def test_a_2dm_mesh_file_opens_as_a_mesh_layer(self):
        from cartogen_ai.core.agent.tools.vector_tools import add_layer_from_path
        path = os.path.join(self.tmp, "m.2dm")
        with open(path, "w") as fh:
            fh.write("MESH2D\nE3T 1 1 2 3 1\nND 1 0 0 0\nND 2 1 0 0\nND 3 0 1 0\n")
        res = add_layer_from_path(path, layer_name="mesh1")
        self.assertTrue(res.get("success"), res)
        self.assertIsInstance(QgsProject.instance().mapLayersByName("mesh1")[0], QgsMeshLayer)

    def test_a_netcdf_raster_opens_as_a_raster_layer(self):
        try:
            from osgeo import gdal
        except ImportError:
            self.skipTest("no osgeo.gdal")
        driver = gdal.GetDriverByName("netCDF")
        if driver is None:
            self.skipTest("this GDAL has no netCDF driver")
        path = os.path.join(self.tmp, "r.nc")
        ds = driver.Create(path, 4, 4, 1, gdal.GDT_Float32)
        ds.SetGeoTransform((0, 1, 0, 4, 0, -1))
        ds.GetRasterBand(1).Fill(3)
        ds = None
        from cartogen_ai.core.agent.tools.vector_tools import add_layer_from_path
        res = add_layer_from_path(path, layer_name="nc1")
        self.assertTrue(res.get("success"), res)
        self.assertIsInstance(QgsProject.instance().mapLayersByName("nc1")[0], QgsRasterLayer)

    def test_add_postgis_layer_reports_an_unknown_connection(self):
        from cartogen_ai.core.agent.tools.data_layer_tools import add_postgis_layer
        self.assertIn("not found", add_postgis_layer("no_such_connection", "t")["error"])
        self.assertIn("error", add_postgis_layer("x/y", "t"))
        self.assertIn("error", add_postgis_layer("c", "bad table"))


PG_HOST = os.environ.get("CARTOGEN_TEST_PG_HOST", "")


@unittest.skipUnless(LIVE and PG_HOST, "needs real QGIS and a PostGIS server (CARTOGEN_TEST_PG_HOST)")
class TestAddPostgisLayerLive(unittest.TestCase):
    CONNECTION = "cartogen_pkgc_conn"

    def setUp(self):
        from tests.test_postgis_live import PG, _admin_connection, _boot_qgis
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        conn = _admin_connection()
        for stmt in ("DROP SCHEMA IF EXISTS cartogen_pkgc CASCADE", "CREATE SCHEMA cartogen_pkgc",
                     "CREATE TABLE cartogen_pkgc.places (id integer PRIMARY KEY, name text, geom geometry(Point, 4326))",
                     "INSERT INTO cartogen_pkgc.places VALUES (1,'a',ST_SetSRID(ST_MakePoint(1,1),4326)),"
                     "(2,'b',ST_SetSRID(ST_MakePoint(2,2),4326))"):
            conn.executeSql(stmt)
        s = QgsSettings()
        base = f"QGIS/connections-postgres/{self.CONNECTION}"
        s.setValue(f"{base}/host", PG["host"])
        s.setValue(f"{base}/port", PG["port"] or "5432")
        s.setValue(f"{base}/database", PG["database"] or "postgres")
        s.setValue(f"{base}/username", PG["user"])
        s.setValue(f"{base}/password", PG["password"])
        self.addCleanup(lambda: QgsSettings().remove(base))

    def test_adds_a_table_as_a_layer_without_leaking_credentials(self):
        from cartogen_ai.core.agent.tools.data_layer_tools import add_postgis_layer
        res = add_postgis_layer(self.CONNECTION, "places", schema="cartogen_pkgc", layer_name="pg_places")
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["feature_count"], 2)
        self.assertNotIn("password", str(res).lower())
        self.assertTrue(QgsProject.instance().mapLayersByName("pg_places")[0].isValid())
        self.assertIn("error", add_postgis_layer(self.CONNECTION, "no_such_table", schema="cartogen_pkgc"))


if __name__ == "__main__":
    unittest.main()
