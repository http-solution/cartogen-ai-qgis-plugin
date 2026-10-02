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

    def test_the_legend_numbers_carry_the_unit(self):
        from cartogen_ai.core.agent.tools.output_style import style_continuous_raster
        arr = np.zeros((20, 20), dtype="float32")
        arr[5:8, 5:8] = 400.0
        layer = self._raster("pop_unit", arr)
        self.assertTrue(style_continuous_raster(layer, "population"))
        legend = layer.renderer().shader().rasterShaderFunction().legendSettings()
        self.assertTrue(legend.useContinuousLegend())
        self.assertEqual(legend.suffix(), " people/cell")
        self.assertTrue(style_continuous_raster(layer, "surface", alg_id="native:slope"))
        self.assertEqual(layer.renderer().shader().rasterShaderFunction().legendSettings().suffix(), " \u00b0")
        self.assertTrue(style_continuous_raster(layer, "density"))
        density = layer.renderer().shader().rasterShaderFunction().legendSettings()
        self.assertEqual((density.minimumLabel(), density.maximumLabel()), ("low", "high"))

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
class TestCsvExportColumns(unittest.TestCase):
    """rc10 smoke test: the exported facilities CSV had no X/Y columns because _write_vector never applied layer_options."""

    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.tmp = tempfile.mkdtemp()

    def _header(self, path):
        with open(path, encoding="utf-8-sig") as fh:
            return fh.readline().strip().split(",")

    def test_a_point_layer_gets_x_and_y_columns_and_a_bom(self):
        from cartogen_ai.core.agent.tools.export_tools import export_to_csv
        layer = _layer("Point", "Pts_csv", ["POINT(44.1 15.9)", "POINT(44.2 16.0)"], fields="&field=name:string")
        QgsProject.instance().addMapLayer(layer)
        out = os.path.join(self.tmp, "pts.csv")
        res = export_to_csv("Pts_csv", output_path=out)
        self.assertTrue(res.get("success"), res)
        header = self._header(out)
        self.assertIn("X", header)
        self.assertIn("Y", header)
        with open(out, "rb") as fh:
            self.assertEqual(fh.read(3), b"\xef\xbb\xbf")

    def test_a_geopackage_backed_point_layer_also_gets_x_and_y(self):
        # The analysis outputs are re-pointed at the results GeoPackage, so the exported layer is OGR-backed.
        from qgis.core import QgsVectorFileWriter, QgsCoordinateTransformContext
        from cartogen_ai.core.agent.tools.export_tools import export_to_csv
        mem = _layer("Point", "Pts_mem", ["POINT(44.1 15.9)"], fields="&field=name:string")
        gpkg = os.path.join(self.tmp, "r.gpkg")
        opts = QgsVectorFileWriter.SaveVectorOptions()
        opts.driverName = "GPKG"
        opts.layerName = "pts"
        QgsVectorFileWriter.writeAsVectorFormatV3(mem, gpkg, QgsCoordinateTransformContext(), opts)
        layer = QgsVectorLayer(f"{gpkg}|layername=pts", "Pts_gpkg", "ogr")
        self.assertTrue(layer.isValid())
        QgsProject.instance().addMapLayer(layer)
        out = os.path.join(self.tmp, "pts_gpkg.csv")
        self.assertTrue(export_to_csv("Pts_gpkg", output_path=out).get("success"))
        header = self._header(out)
        self.assertIn("X", header)
        self.assertIn("Y", header)

    def test_a_polygon_layer_keeps_a_wkt_column(self):
        from cartogen_ai.core.agent.tools.export_tools import export_to_csv
        layer = _layer("Polygon", "Poly_csv", ["POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"])
        QgsProject.instance().addMapLayer(layer)
        out = os.path.join(self.tmp, "poly.csv")
        self.assertTrue(export_to_csv("Poly_csv", output_path=out).get("success"))
        self.assertIn("WKT", self._header(out))


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestAutoArrangeOrder(unittest.TestCase):
    """rc10 smoke test: the original facilities layer stayed above its classified copy, hiding the green/red points."""

    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _names_top_to_bottom(self):
        return [n.name() for n in QgsProject.instance().layerTreeRoot().children()]

    def test_an_analysis_output_is_drawn_above_its_source_layer(self):
        from cartogen_ai.core.agent.tools.styling_tools import auto_arrange_layer_order
        project = QgsProject.instance()
        project.addMapLayer(_layer("Point", "Facilities_access_1", ["POINT(44 15)"]))
        project.addMapLayer(_layer("Point", "Facilities", ["POINT(44 15)"]))     # added last -> sits on top by default
        project.addMapLayer(_layer("LineString", "Roads", ["LINESTRING(44 15, 45 16)"]))
        self.assertTrue(auto_arrange_layer_order().get("success"))
        names = self._names_top_to_bottom()
        self.assertLess(names.index("Facilities_access_1"), names.index("Facilities"))
        self.assertLess(names.index("Facilities"), names.index("Roads"))

    def test_a_data_raster_is_ordered_above_a_web_basemap(self):
        # rc10 smoke test: the fetched population raster ended UNDER the OSM basemap and was hidden by it.
        from cartogen_ai.core.agent.tools.styling_tools import auto_arrange_layer_order
        project = QgsProject.instance()
        arr = np.zeros((10, 10), dtype="float32")
        data = QgsRasterLayer(_tif(os.path.join(tempfile.mkdtemp(), "d.tif"), arr), "Data_raster")
        self.assertTrue(data.isValid())
        project.addMapLayer(data)
        basemap = QgsRasterLayer("type=xyz&url=https://example.invalid/{z}/{x}/{y}.png&zmax=19&zmin=0", "OSM Standard", "wms")
        if not basemap.isValid():
            self.skipTest("no XYZ provider in this QGIS build")
        project.addMapLayer(basemap)                              # added last -> on top of the data raster by default
        self.assertTrue(auto_arrange_layer_order().get("success"))
        names = self._names_top_to_bottom()
        self.assertLess(names.index("Data_raster"), names.index("OSM Standard"))

    def test_reordering_keeps_each_layers_visibility(self):
        from cartogen_ai.core.agent.tools.styling_tools import auto_arrange_layer_order
        project = QgsProject.instance()
        hidden = _layer("Point", "Hidden_pts", ["POINT(44 15)"])
        shown = _layer("Point", "Shown_pts", ["POINT(44 15)"])
        project.addMapLayer(hidden)
        project.addMapLayer(shown)
        root = project.layerTreeRoot()
        root.findLayer(hidden.id()).setItemVisibilityChecked(False)
        self.assertTrue(auto_arrange_layer_order().get("success"))
        self.assertFalse(root.findLayer(hidden.id()).itemVisibilityChecked())
        self.assertTrue(root.findLayer(shown.id()).itemVisibilityChecked())


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestAutoLabels(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _named(self, name, count, field="name"):
        layer = _layer("Point", name, [f"POINT({i} 1)" for i in range(count)], fields=f"&field={field}:string")
        QgsProject.instance().addMapLayer(layer)
        return layer

    def test_a_small_named_layer_is_labelled_with_its_name_field(self):
        from cartogen_ai.core.agent.tools.output_style import style_auto_labels
        layer = self._named("Clinics_lbl", 5)
        self.assertEqual(style_auto_labels(layer), "name")
        self.assertTrue(layer.labelsEnabled())
        self.assertEqual(layer.labeling().settings().fieldName, "name")

    def test_a_large_layer_is_left_unlabelled(self):
        from cartogen_ai.core.agent.tools.output_style import style_auto_labels
        layer = self._named("Many_lbl", 120)
        self.assertIsNone(style_auto_labels(layer))
        self.assertFalse(layer.labelsEnabled())

    def test_a_layer_without_a_name_field_is_left_unlabelled(self):
        from cartogen_ai.core.agent.tools.output_style import style_auto_labels
        layer = self._named("Codes_lbl", 5, field="pcode")
        self.assertIsNone(style_auto_labels(layer))


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

    def test_the_graticule_is_thin_with_small_whole_number_annotations(self):
        # rc11 smoke test S7: solid black grid lines and '4880000.000' annotations overran the info row and the page edges.
        _, layout, _ = self._layout()
        grid = layout.itemById("MAP_MAIN").grids().grid(0)
        self.assertIsNotNone(grid)
        self.assertEqual(grid.annotationPrecision(), 0)
        self.assertLessEqual(grid.annotationTextFormat().size(), 7)

    def test_access_map_template_fits_the_reach_layer_and_orders_the_legend(self):
        project = QgsProject.instance()
        reach = _layer("Polygon", "Clinics_reachable_area", ["POLYGON((44 15, 44.5 15, 44.5 15.5, 44 15.5, 44 15))"])
        access = _layer("Point", "Clinics_access_30", ["POINT(44.1 15.1)"])
        project.addMapLayer(access)
        project.addMapLayer(reach)
        res, layout, _ = self._layout(template="access_map")
        self.assertEqual(res["template"], "access_map")
        self.assertEqual(res["legend_layers"][:2], ["Clinics_reachable_area", "Clinics_access_30"])
        self.assertIn("reachable area", layout.itemById("BODY_TEXT").text())

    def test_the_masthead_colour_comes_from_settings(self):
        from qgis.core import QgsSettings
        from cartogen_ai.infrastructure.settings_keys import SETTINGS_LAYOUT_MASTHEAD_COLOR as KEY
        settings = QgsSettings()
        settings.setValue(KEY, "#ffeeaa")
        self.addCleanup(settings.remove, KEY)
        _, layout, _ = self._layout()
        title = layout.itemById("TITLE")
        self.assertEqual(title.backgroundColor().name(), "#ffeeaa")
        self.assertEqual(title.textFormat().color().name(), "#1f2d3a")      # light background -> dark text

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
