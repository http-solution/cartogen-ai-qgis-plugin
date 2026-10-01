# -*- coding: utf-8 -*-
"""Live-QGIS tests for output styling, the processing allowlist extension and print layout styling. Written without a QGIS
install: the first CI run is their first execution."""
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from qgis.core import QgsApplication, QgsFeature, QgsGeometry, QgsProject, QgsRasterLayer, QgsVectorLayer
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False

try:
    import numpy as np
    from osgeo import gdal, osr
    GDAL_AVAILABLE = True
except ImportError:
    GDAL_AVAILABLE = False


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


def _layer(kind, name, wkts, fields=""):
    layer = QgsVectorLayer(f"{kind}?crs=EPSG:4326{fields}", name, "memory")
    feats = []
    for wkt in wkts:
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(wkt))
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    return layer


def _tif(path, array, origin=(40.0, 20.0), cell=0.01):
    drv = gdal.GetDriverByName("GTiff")
    ds = drv.Create(path, array.shape[1], array.shape[0], 1, gdal.GDT_Float32)
    ds.SetGeoTransform((origin[0], cell, 0, origin[1], 0, -cell))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    ds.SetProjection(srs.ExportToWkt())
    band = ds.GetRasterBand(1)
    band.WriteArray(array)
    band.SetNoDataValue(-9999)
    ds.FlushCache()
    ds = None
    return path


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestAllowlistExtensionsExistInQgis(unittest.TestCase):
    """Every algorithm id added to the allowlist must exist in the real registry (a wrong id fails here, not for the model)."""

    def setUp(self):
        _boot_qgis()
        import processing  # noqa: F401  -- initialises the processing framework
        from qgis.analysis import QgsNativeAlgorithms
        registry = QgsApplication.processingRegistry()
        if registry.providerById("native") is None:
            registry.addProvider(QgsNativeAlgorithms())

    def test_every_extension_id_is_a_real_algorithm(self):
        from cartogen_ai.core.agent.tools._processing_allowlist import ANALYSIS_EXTENSIONS
        registry = QgsApplication.processingRegistry()
        missing = sorted(a for a in ANALYSIS_EXTENSIONS if registry.algorithmById(a) is None)
        self.assertEqual(missing, [], f"not in this QGIS: {missing}")


@unittest.skipUnless(QGIS_LIVE_AVAILABLE and GDAL_AVAILABLE, "requires real QGIS + gdal + numpy")
class TestRasterStyles(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.tmp = tempfile.mkdtemp()

    def _raster(self, name, array):
        layer = QgsRasterLayer(_tif(os.path.join(self.tmp, name + ".tif"), array), name)
        self.assertTrue(layer.isValid())
        QgsProject.instance().addMapLayer(layer)
        return layer

    def test_population_is_pseudocolour_with_a_transparent_zero(self):
        from cartogen_ai.core.agent.tools.output_style import style_continuous_raster
        arr = np.zeros((20, 20), dtype="float32")
        arr[5:8, 5:8] = 400.0
        arr[10, 10] = 900.0
        layer = self._raster("pop", arr)
        self.assertTrue(style_continuous_raster(layer, "population"))
        renderer = layer.renderer()
        self.assertEqual(renderer.type(), "singlebandpseudocolor")
        shader = renderer.shader().rasterShaderFunction()
        items = shader.colorRampItemList()
        self.assertEqual(items[0].color.alpha(), 0)           # empty land shows the basemap
        self.assertEqual(items[-1].color.alpha(), 255)
        self.assertAlmostEqual(items[-1].value, 900.0, places=1)

    def test_a_surface_is_opaque_from_min_to_max(self):
        from cartogen_ai.core.agent.tools.output_style import style_continuous_raster
        arr = np.linspace(10, 50, 400, dtype="float32").reshape(20, 20)
        layer = self._raster("surf", arr)
        self.assertTrue(style_continuous_raster(layer, "surface"))
        items = layer.renderer().shader().rasterShaderFunction().colorRampItemList()
        self.assertEqual(items[0].color.alpha(), 255)
        self.assertAlmostEqual(items[0].value, 10.0, places=1)
        self.assertAlmostEqual(items[-1].value, 50.0, places=1)

    def test_a_raster_algorithm_through_the_tool_loads_and_is_styled(self):
        from cartogen_ai.core.agent.tools.processing_allowlist_tools import run_allowlisted_processing_algorithm
        arr = (np.arange(400, dtype="float32").reshape(20, 20)) * 3.0
        self._raster("dem", arr)
        res = run_allowlisted_processing_algorithm("native:slope", {"INPUT": "dem"}, new_layer_name="slope_out")
        self.assertTrue(res.get("success"), res)
        layers = QgsProject.instance().mapLayersByName("slope_out")
        self.assertEqual(len(layers), 1, res)               # before the fix: "ran successfully with no new layer output"
        self.assertTrue(layers[0].isValid())
        self.assertEqual(res.get("styled_as"), "raster:surface")


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestVectorOutputStyles(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def test_points_get_one_consistent_look(self):
        from cartogen_ai.core.agent.tools.output_style import style_points_default
        layer = _layer("Point", "p", ["POINT(0 0)"])
        self.assertTrue(style_points_default(layer))
        self.assertEqual(layer.renderer().type(), "singleSymbol")
        self.assertEqual(layer.renderer().symbol().color().name(), "#1d6fa5")

    def test_a_buffer_from_the_allowlisted_tool_is_styled_as_a_proximity_buffer(self):
        from cartogen_ai.core.agent.tools.processing_allowlist_tools import run_allowlisted_processing_algorithm
        QgsProject.instance().addMapLayer(_layer("Point", "pts", ["POINT(44 15.9)", "POINT(44.2 16)"]))
        res = run_allowlisted_processing_algorithm("native:buffer", {"INPUT": "pts", "DISTANCE": 0.01},
                                                   new_layer_name="pts_buffer")
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res.get("styled_as"), "vector:proximity_buffer")

    def test_countpointsinpolygon_runs_through_the_tool(self):
        from cartogen_ai.core.agent.tools.processing_allowlist_tools import run_allowlisted_processing_algorithm
        project = QgsProject.instance()
        project.addMapLayer(_layer("Polygon", "areas", ["POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))", "POLYGON((2 0, 3 0, 3 1, 2 1, 2 0))"]))
        project.addMapLayer(_layer("Point", "clinics", ["POINT(0.5 0.5)", "POINT(0.6 0.4)", "POINT(2.5 0.5)"]))
        res = run_allowlisted_processing_algorithm(
            "native:countpointsinpolygon", {"POLYGONS": "areas", "POINTS": "clinics"}, new_layer_name="clinics_per_area")
        self.assertTrue(res.get("success"), res)
        out = project.mapLayersByName("clinics_per_area")[0]
        counts = sorted(int(f["NUMPOINTS"]) for f in out.getFeatures())
        self.assertEqual(counts, [1, 2])


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestPrintLayoutStyling(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.tmp = tempfile.mkdtemp()
        project = QgsProject.instance()
        self.visible = _layer("Point", "Clinics", ["POINT(44 15.9)", "POINT(44.1 16)"])
        self.hidden = _layer("LineString", "Origin_service_area_lines_0", ["LINESTRING(44 15.9, 44.1 16)"])
        self.also_hidden = _layer("Polygon", "Scratch", ["POLYGON((44 15, 45 15, 45 16, 44 16, 44 15))"])
        for layer in (self.visible, self.hidden, self.also_hidden):
            project.addMapLayer(layer)
        root = project.layerTreeRoot()
        root.findLayer(self.also_hidden.id()).setItemVisibilityChecked(False)

    def _layout(self, **kw):
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        out = os.path.join(self.tmp, "layout.png")
        res = create_print_layout("Access to care", output_path=out, dpi=72, **kw)
        self.assertTrue(res.get("success"), res)
        layout = QgsProject.instance().layoutManager().layoutByName(res["layout_name"])
        self.assertIsNotNone(layout)
        return res, layout, out

    def test_the_legend_lists_only_visible_thematic_layers(self):
        res, layout, _ = self._layout()
        self.assertEqual(res["legend_layers"], ["Clinics"])          # not the hidden scratch, not the "_lines_" helper
        legend = layout.itemById("LEGEND")
        self.assertFalse(legend.autoUpdateModel())
        names = [n.layer().name() for n in legend.model().rootGroup().findLayers()]
        self.assertEqual(names, ["Clinics"])
        self.assertTrue(legend.legendFilterByMapEnabled())

    def test_title_is_a_masthead_and_panels_have_frames(self):
        _, layout, _ = self._layout(body_text="Finding one\nFinding two")
        title = layout.itemById("TITLE")
        self.assertAlmostEqual(title.textFormat().size(), 20.0, places=1)
        self.assertTrue(title.hasBackground())
        self.assertTrue(layout.itemById("MAP_MAIN").frameEnabled())
        self.assertTrue(layout.itemById("LEGEND").frameEnabled())
        self.assertTrue(layout.itemById("BODY_TEXT").frameEnabled())

    def test_the_info_row_carries_the_preparation_date(self):
        _, layout, _ = self._layout()
        self.assertIn("Prepared ", layout.itemById("MAP_INFO").text())

    def test_a_sensitive_visible_layer_puts_a_classification_in_the_footer(self):
        from cartogen_ai.core.models import sensitivity
        sensitivity.set_layer_sensitivity(self.visible, "SENSITIVE", "test")
        res, layout, _ = self._layout()
        self.assertEqual(res.get("classification"), "CLASSIFICATION: SENSITIVE")
        self.assertTrue(layout.itemById("FOOTER").text().startswith("CLASSIFICATION: SENSITIVE"))

    def test_no_classification_for_an_open_layer(self):
        res, layout, _ = self._layout()
        self.assertNotIn("classification", res)
        self.assertFalse(layout.itemById("FOOTER").text().startswith("CLASSIFICATION"))

    def test_the_styled_layout_still_exports(self):
        _, _, out = self._layout()
        self.assertTrue(os.path.exists(out))
        self.assertGreater(os.path.getsize(out), 1000)

    def test_styling_never_moves_the_items(self):
        _, layout, _ = self._layout()
        # positions are the live-verified geometry in create_print_layout; the style pass must not touch them
        self.assertAlmostEqual(layout.itemById("MAP_MAIN").positionWithUnits().x(), 15.0, places=1)
        self.assertAlmostEqual(layout.itemById("TITLE").positionWithUnits().y(), 8.0, places=1)


if __name__ == "__main__":
    unittest.main()
