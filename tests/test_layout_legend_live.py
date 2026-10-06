# -*- coding: utf-8 -*-
"""rc18 R7/N8: the legend must not list a raster that lies outside the map. Written without a local QGIS: CI's first run is its first execution."""
import os
import unittest

try:
    from qgis.core import (QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry, QgsLayoutItemMap, QgsLayoutSize, QgsPrintLayout,
                           QgsProject, QgsRasterLayer, QgsRectangle, QgsUnitTypes, QgsVectorLayer)
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False

try:
    import numpy as np
    from osgeo import gdal  # noqa: F401
    GDAL_AVAILABLE = True
except ImportError:
    GDAL_AVAILABLE = False


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


@unittest.skipUnless(QGIS_LIVE_AVAILABLE and GDAL_AVAILABLE, "requires real QGIS with GDAL bindings and numpy")
class TestLegendOnlyListsWhatTheMapShows(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        from cartogen_ai.core.agent.tools import raster_numpy
        self.points = QgsVectorLayer("Point?crs=EPSG:4326&field=n:string", "points", "memory")
        f = QgsFeature(self.points.fields())
        f.setGeometry(QgsGeometry.fromWkt("POINT(44.0 15.0)"))
        self.points.dataProvider().addFeatures([f])
        self.points.updateExtents()
        wkt = QgsCoordinateReferenceSystem("EPSG:4326").toWkt()
        self.near_path = raster_numpy.write_single_band(np.full((10, 10), 5, dtype="uint8"),
                                                        {"geotransform": (43.95, 0.01, 0.0, 15.05, 0.0, -0.01), "projection": wkt}, nodata=0)
        self.far_path = raster_numpy.write_single_band(np.full((10, 10), 5, dtype="uint8"),
                                                       {"geotransform": (60.0, 0.01, 0.0, 30.0, 0.0, -0.01), "projection": wkt}, nodata=0)
        for p in (self.near_path, self.far_path):
            self.addCleanup(lambda p=p: os.path.exists(p) and os.remove(p))
        self.near = QgsRasterLayer(self.near_path, "near_dem")
        self.far = QgsRasterLayer(self.far_path, "far_dem")
        self.assertTrue(self.near.isValid() and self.far.isValid())
        QgsProject.instance().addMapLayers([self.points, self.near, self.far])
        layout = QgsPrintLayout(QgsProject.instance())
        layout.initializeDefaults()
        self.map_item = QgsLayoutItemMap(layout)
        layout.addLayoutItem(self.map_item)
        # a new map item is 0 x 0 mm; setExtent() resizes it to the extent's aspect ratio, so give it a real size first
        from cartogen_ai.core.agent.tools.layout_tools import LAYOUT_MM
        self.map_item.attemptResize(QgsLayoutSize(100, 100, LAYOUT_MM))
        self.map_item.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
        self.map_item.setExtent(QgsRectangle(43.9, 14.9, 44.1, 15.1))
        self.layout = layout

    def test_an_off_map_raster_is_dropped_and_on_map_layers_stay(self):
        from cartogen_ai.core.agent.tools.layout_style import legend_layers_on_map
        pairs = [(self.points.id(), self.points), (self.near.id(), self.near), (self.far.id(), self.far)]
        kept = [layer.name() for _i, layer in legend_layers_on_map(pairs, self.map_item)]
        self.assertEqual(kept, ["points", "near_dem"],
                         f"map extent {self.map_item.extent().toString()}, near {self.near.extent().toString()}, "
                         f"map crs {self.map_item.crs().authid()}, near crs {self.near.crs().authid()!r}")

    def test_a_layer_with_no_extent_is_kept_not_dropped_on_a_guess(self):
        from cartogen_ai.core.agent.tools.layout_style import legend_layers_on_map
        empty = QgsVectorLayer("Point?crs=EPSG:4326", "empty", "memory")
        QgsProject.instance().addMapLayer(empty)
        kept = [layer.name() for _i, layer in legend_layers_on_map([(empty.id(), empty)], self.map_item)]
        self.assertEqual(kept, ["empty"])

    def test_graticule_annotations_on_the_right_and_top_are_hidden(self):
        from qgis.core import QgsLayoutItemMapGrid
        from cartogen_ai.core.agent.tools.layout_tools import _soften_graticule
        grid = QgsLayoutItemMapGrid("g", self.map_item)
        _soften_graticule(grid)
        display = getattr(QgsLayoutItemMapGrid, "DisplayMode", QgsLayoutItemMapGrid)
        side = getattr(QgsLayoutItemMapGrid, "BorderSide", QgsLayoutItemMapGrid)
        self.assertEqual(grid.annotationDisplay(side.Right), display.HideAll)
        self.assertEqual(grid.annotationDisplay(side.Top), display.HideAll)
        self.assertNotEqual(grid.annotationDisplay(side.Left), display.HideAll)


if __name__ == "__main__":
    unittest.main()
