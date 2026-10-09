# -*- coding: utf-8 -*-
"""Live-QGIS checks of split_lines_by_zones and generate_contours against geometry with known answers. Written without
hand-testing; the Docker QGIS run is the only execution evidence."""
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    import numpy
    from osgeo import gdal, osr
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsRasterLayer, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


def _boot():
    from tests.test_chat_widget_live import _boot_qgis
    _boot_qgis()
    try:
        from processing.core.Processing import Processing
        Processing.initialize()
    except Exception:
        pass


@unittest.skipUnless(LIVE, "requires real QGIS + gdal + numpy")
class TestCorridorToolsLive(unittest.TestCase):
    def setUp(self):
        _boot()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _layers(self, centres, radius, segments=1):
        """A 10 km east-west line at the UTM 38N central meridian (EPSG:32638) in `segments` pieces, and circular zones."""
        line = QgsVectorLayer("LineString?crs=EPSG:32638&field=name:string", "road", "memory")
        feats = []
        edges = [500000 + 10000 * i / segments for i in range(segments + 1)]
        for a, b in zip(edges, edges[1:]):
            f = QgsFeature(line.fields())
            f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(a, 1700000), QgsPointXY(b, 1700000)]))
            f.setAttributes(["seg"])
            feats.append(f)
        line.dataProvider().addFeatures(feats)
        zones = QgsVectorLayer("Polygon?crs=EPSG:32638&field=id:integer", "zones", "memory")
        zfeats = []
        for i, x in enumerate(centres):
            f = QgsFeature(zones.fields())
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, 1700000)).buffer(radius, 64))
            f.setAttributes([i])
            zfeats.append(f)
        zones.dataProvider().addFeatures(zfeats)
        QgsProject.instance().addMapLayer(line)
        QgsProject.instance().addMapLayer(zones)

    def test_split_reports_total_and_longest_segment_with_known_geometry(self):
        from cartogen_ai.core.agent.tools.corridor_tools import split_lines_by_zones
        self._layers([502000, 507000], 1000)         # zones cover 1-3 km and 6-8 km: clear 1 + 3 + 2 = 6 km, longest 3 km
        res = split_lines_by_zones("road", "zones")
        self.assertTrue(res.get("success"), res)
        self.assertAlmostEqual(res["clear_length_km"], 6.0, delta=0.05)
        self.assertAlmostEqual(res["compromised_length_km"], 4.0, delta=0.05)
        self.assertAlmostEqual(res["longest_clear_segment_km"], 3.0, delta=0.03)
        self.assertEqual((res["clear_segment_count"], res["compromised_segment_count"]), (3, 2))
        layer = QgsProject.instance().mapLayersByName(res["layer_name"])[0]
        self.assertEqual(sorted({f["status"] for f in layer.getFeatures()}), ["clear", "compromised"])
        self.assertEqual(layer.renderer().type(), "categorizedSymbol")
        colours = {c.label(): c.symbol().color().name() for c in layer.renderer().categories()}
        self.assertEqual(colours["Compromised"], "#d7191c")
        self.assertEqual(colours["Clear"], "#1a9641")

    def test_a_road_stored_as_many_segments_is_one_continuous_road(self):
        from cartogen_ai.core.agent.tools.corridor_tools import split_lines_by_zones
        self._layers([502000, 507000], 1000, segments=10)          # same road, 10 pieces of 1 km
        res = split_lines_by_zones("road", "zones")
        self.assertTrue(res.get("success"), res)
        self.assertAlmostEqual(res["longest_clear_segment_km"], 3.0, delta=0.03)       # not 1 km: pieces are joined first
        self.assertEqual(res["clear_segment_count"], 3)

    def test_no_overlap_is_one_clear_piece_and_errors_are_plain(self):
        from cartogen_ai.core.agent.tools.corridor_tools import split_lines_by_zones
        self._layers([520000], 500)                                   # far east of the 10 km road
        res = split_lines_by_zones("road", "zones")
        self.assertAlmostEqual(res["clear_length_km"], 10.0, delta=0.05)
        self.assertEqual(res["compromised_segment_count"], 0)
        self.assertIn("not a polygon layer", split_lines_by_zones("road", "road")["error"])
        self.assertIn("not found", split_lines_by_zones("nope", "zones")["error"])

    def test_geographic_lines_are_measured_on_the_ellipsoid(self):
        from cartogen_ai.core.agent.tools.corridor_tools import split_lines_by_zones
        line = QgsVectorLayer("LineString?crs=EPSG:4326&field=n:string", "geo_road", "memory")
        f = QgsFeature(line.fields())
        f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(45.0, 15.0), QgsPointXY(45.1, 15.0)]))   # ~10.7 km along a parallel
        line.dataProvider().addFeatures([f])
        zones = QgsVectorLayer("Polygon?crs=EPSG:4326&field=n:string", "geo_zones", "memory")
        z = QgsFeature(zones.fields())
        z.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(45.05, 15.0)).buffer(0.01, 32))
        zones.dataProvider().addFeatures([z])
        QgsProject.instance().addMapLayer(line)
        QgsProject.instance().addMapLayer(zones)
        res = split_lines_by_zones("geo_road", "geo_zones")
        self.assertTrue(res.get("success"), res)
        self.assertAlmostEqual(res["total_length_km"], 10.74, delta=0.1)
        self.assertIn("EPSG:326", res["measured_in"])

    def _dem(self, name, rows=100, cols=100, pixel=10.0):
        path = os.path.join(tempfile.mkdtemp(prefix="cartogen_dem_"), f"{name}.tif")
        ds = gdal.GetDriverByName("GTiff").Create(path, cols, rows, 1, gdal.GDT_Float32)
        ds.SetGeoTransform((500000.0, pixel, 0, 1700000.0 + rows * pixel, 0, -pixel))
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(32638)
        ds.SetProjection(srs.ExportToWkt())
        yy, xx = numpy.mgrid[0:rows, 0:cols]
        ds.GetRasterBand(1).WriteArray((xx * 1.0).astype("float32"))            # a ramp rising 1 m per 10 m pixel, 0..99 m
        ds.FlushCache()
        ds = None
        layer = QgsRasterLayer(path, name)
        self.assertTrue(layer.isValid())
        QgsProject.instance().addMapLayer(layer)

    def test_contours_at_a_known_interval_and_honest_metadata(self):
        from cartogen_ai.core.agent.tools.corridor_tools import generate_contours
        self._dem("ramp")
        res = generate_contours("ramp", interval=10)
        self.assertTrue(res.get("success"), res)
        layer = QgsProject.instance().mapLayersByName(res["layer_name"])[0]
        levels = sorted({round(f["ELEV"]) for f in layer.getFeatures()})
        self.assertEqual(levels, [0, 10, 20, 30, 40, 50, 60, 70, 80, 90])     # 0 is the DEM's own first column
        self.assertEqual(res["dem"]["pixel_size_x"], 10.0)
        self.assertEqual(res["dem"]["crs"], "EPSG:32638")
        self.assertIn("do not describe the contours as accurate", res["note"])

    def test_bad_interval_and_non_raster_are_refused(self):
        from cartogen_ai.core.agent.tools.corridor_tools import generate_contours
        self._dem("ramp")
        self.assertIn("greater than zero", generate_contours("ramp", interval=0)["error"])
        self.assertIn("must be a number", generate_contours("ramp", interval="x")["error"])
        self._layers([502000], 500)
        self.assertIn("not a raster", generate_contours("road")["error"])


if __name__ == "__main__":
    unittest.main()
