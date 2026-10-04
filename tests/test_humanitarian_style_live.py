# -*- coding: utf-8 -*-
"""Live-QGIS tests for tools/humanitarian_style.py and its call sites. Written without a QGIS install: CI's first run is their first execution."""
import unittest

try:
    from qgis.core import (QgsCategorizedSymbolRenderer, QgsFeature, QgsGeometry, QgsProject, QgsRasterLayer,
                           QgsSingleBandPseudoColorRenderer, QgsSingleSymbolRenderer, QgsVectorLayer)
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


def _add(layer, rows):
    feats = []
    for wkt, attrs in rows:
        f = QgsFeature(layer.fields())
        if wkt:
            f.setGeometry(QgsGeometry.fromWkt(wkt))
        f.setAttributes(attrs)
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    QgsProject.instance().addMapLayer(layer)
    return layer


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestHumanitarianStyles(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _categories(self, layer):
        r = layer.renderer()
        self.assertIsInstance(r, QgsCategorizedSymbolRenderer)
        return {c.value(): c.label() for c in r.categories()}

    def test_task_grid_is_categorised_by_priority(self):
        from cartogen_ai.core.agent.tools.humanitarian_style import style_task_grid
        layer = _add(QgsVectorLayer("Polygon?crs=EPSG:4326&field=task_id:string&field=priority:string", "tasks", "memory"),
                     [("POLYGON((0 0,1 0,1 1,0 1,0 0))", ["a", "High"]), ("POLYGON((1 0,2 0,2 1,1 1,1 0))", ["b", "Low"]),
                      ("POLYGON((2 0,3 0,3 1,2 1,2 0))", ["c", None])])
        self.assertTrue(style_task_grid(layer))
        cats = self._categories(layer)
        self.assertEqual(set(cats.values()), {"High", "Low", "unranked"})

    def test_an_unranked_grid_gets_one_neutral_symbol(self):
        from cartogen_ai.core.agent.tools.humanitarian_style import style_task_grid
        layer = _add(QgsVectorLayer("Polygon?crs=EPSG:4326&field=task_id:string&field=priority:string", "tasks", "memory"),
                     [("POLYGON((0 0,1 0,1 1,0 1,0 0))", ["a", None])])
        self.assertTrue(style_task_grid(layer))
        self.assertIsInstance(layer.renderer(), QgsSingleSymbolRenderer)

    def test_sample_points_get_a_colour_per_stratum(self):
        from cartogen_ai.core.agent.tools.humanitarian_style import style_sample_points
        layer = _add(QgsVectorLayer("Point?crs=EPSG:4326&field=stratum:string", "sample", "memory"),
                     [("POINT(0 0)", ["North"]), ("POINT(1 1)", ["South"]), ("POINT(2 2)", ["North"])])
        self.assertTrue(style_sample_points(layer))
        self.assertEqual(set(self._categories(layer).values()), {"North", "South"})

    def test_hazard_layers(self):
        from cartogen_ai.core.agent.tools.humanitarian_style import style_hazard_layer
        g = _add(QgsVectorLayer("Point?crs=EPSG:4326&field=alert_level:string", "gdacs", "memory"),
                 [("POINT(0 0)", ["Red"]), ("POINT(1 1)", ["Orange"])])
        self.assertTrue(style_hazard_layer(g, "gdacs"))
        self.assertEqual(set(self._categories(g).values()), {"Red", "Orange", "Green", "other"})
        f = _add(QgsVectorLayer("Point?crs=EPSG:4326&field=frp:double", "fires", "memory"), [("POINT(0 0)", [1.0])])
        self.assertTrue(style_hazard_layer(f, "fires"))
        self.assertIsInstance(f.renderer(), QgsSingleSymbolRenderer)
        e = _add(QgsVectorLayer("Point?crs=EPSG:4326&field=category:string", "eonet", "memory"),
                 [("POINT(0 0)", ["Floods"]), ("POINT(1 1)", ["Wildfires"])])
        self.assertTrue(style_hazard_layer(e, "eonet"))
        self.assertFalse(style_hazard_layer(e, "unknown"))

    def test_new_hazard_layer_from_the_tool_is_styled_on_creation_only(self):
        from cartogen_ai.core.agent.tools.hazard_monitoring_tools import add_gdacs_disaster_alerts_layer_main_thread_phase
        fetched = {"alerts": [{"lon": 44.0, "lat": 15.0, "event_id": "1", "event_type": "FL", "name": "x", "description": "d",
                               "alert_level": "Red", "country": "Yemen", "from_date": "", "to_date": ""}]}
        res = add_gdacs_disaster_alerts_layer_main_thread_phase(fetched)
        self.assertTrue(res.get("success"), res)
        layer = QgsProject.instance().mapLayersByName("GDACS Disaster Alerts")[0]
        self.assertIsInstance(layer.renderer(), QgsCategorizedSymbolRenderer)

    def test_barrier_tool_draws_the_affected_segments(self):
        from cartogen_ai.core.agent.tools.barrier_tools import apply_network_barriers
        _add(QgsVectorLayer("LineString?crs=EPSG:4326&field=speed:double", "roads", "memory"),
             [("LINESTRING(44.000 15.000, 44.010 15.000)", [60.0]), ("LINESTRING(44.000 15.010, 44.010 15.010)", [60.0])])
        _add(QgsVectorLayer("Point?crs=EPSG:4326&field=n:string", "bridge", "memory"), [("POINT(44.005 15.0)", ["b"])])
        res = apply_network_barriers("roads", "bridge", buffer_m=50, speed_field="speed")
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res.get("affected_layer"), "roads_barrier_affected")
        layer = QgsProject.instance().mapLayersByName("roads_barrier_affected")[0]
        self.assertEqual(layer.featureCount(), 1)
        again = apply_network_barriers("roads", "bridge", buffer_m=50, speed_field="speed")      # replaced, not duplicated
        self.assertTrue(again.get("success"), again)
        self.assertEqual(len(QgsProject.instance().mapLayersByName("roads_barrier_affected")), 1)

    def test_difference_raster_gets_a_diverging_ramp(self):
        import os
        import tempfile
        from osgeo import gdal
        from cartogen_ai.core.agent.tools.humanitarian_style import style_diverging_raster
        path = os.path.join(tempfile.mkdtemp(prefix="cartogen_div_"), "diff.tif")
        ds = gdal.GetDriverByName("GTiff").Create(path, 2, 2, 1, gdal.GDT_Float32)
        ds.SetGeoTransform((0, 1, 0, 2, 0, -1))
        ds.GetRasterBand(1).WriteArray([[-5.0, 0.0], [2.0, 8.0]])
        ds.FlushCache()
        ds = None
        layer = QgsRasterLayer(path, "diff")
        QgsProject.instance().addMapLayer(layer)
        self.assertTrue(style_diverging_raster(layer))
        self.assertIsInstance(layer.renderer(), QgsSingleBandPseudoColorRenderer)


if __name__ == "__main__":
    unittest.main()
