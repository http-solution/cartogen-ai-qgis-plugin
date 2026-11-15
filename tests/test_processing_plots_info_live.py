"""PLAN-023 R11-5 (PLAN-006 E2b and E2a) in real QGIS, through the generic tool: each of the eight chart algorithms writes a complete HTML page to a temporary file the plugin chose (a path the
caller supplies is ignored) and reports its path; the three file-information algorithms return a bounded text excerpt that names the real driver of the real file; an excerpt never exceeds the
limit. native:generateelevationprofileimage is only ATTEMPTED here and its outcome printed on a line starting 'ELEVPROFILE' (it is decided from that line, not asserted). Written without a QGIS
install: CI's first run is its first execution."""
import os
import tempfile
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsRasterLayer, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False

PLOTS = {
    "qgis:barplot": {"INPUT": "towns", "NAME_FIELD": "name", "VALUE_FIELD": "pop"},
    "qgis:boxplot": {"INPUT": "towns", "NAME_FIELD": "name", "VALUE_FIELD": "pop"},
    "qgis:meanandstandarddeviationplot": {"INPUT": "towns", "NAME_FIELD": "name", "VALUE_FIELD": "pop"},
    "qgis:polarplot": {"INPUT": "towns", "VALUE_FIELD": "pop"},       # no NAME_FIELD: the first CI run of this test showed the algorithm has only INPUT and VALUE_FIELD
    "qgis:rasterlayerhistogram": {"INPUT": "dem", "BAND": 1, "BINS": 10},
    "qgis:vectorlayerhistogram": {"INPUT": "towns", "FIELD": "pop", "BINS": 5},
    "qgis:vectorlayerscatterplot": {"INPUT": "towns", "XFIELD": "pop", "YFIELD": "pop2"},
    "qgis:scatter3dplot": {"INPUT": "towns", "XFIELD": "pop", "YFIELD": "pop2", "ZFIELD": "pop"},
}


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestPlotsAndInfoLive(unittest.TestCase):
    def setUp(self):
        from tests._geometry_probe import _make_rasters
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.folder = tempfile.mkdtemp()
        for name, path in _make_rasters(self.folder).items():
            QgsProject.instance().addMapLayer(QgsRasterLayer(path, name))
        memory = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string&field=pop:double&field=pop2:double", "towns_memory", "memory")
        feats = []
        for i, (x, y, pop) in enumerate(((0.5, 0.5, 10.0), (1.0, 1.2, 40.0), (1.1, 0.4, 70.0), (3.0, 3.1, 100.0), (3.4, 3.3, 5.0), (2.2, 1.9, 60.0))):
            f = QgsFeature(memory.fields())
            f.setGeometry(QgsGeometry.fromWkt(f"POINT({x} {y})"))
            f.setAttributes([f"t{i % 3}", pop, pop * 2.0])
            feats.append(f)
        memory.dataProvider().addFeatures(feats)
        import processing
        self.gpkg = os.path.join(self.folder, "towns.gpkg")
        processing.run("native:savefeatures", {"INPUT": memory, "OUTPUT": self.gpkg, "LAYER_NAME": "towns"})
        towns = QgsVectorLayer(self.gpkg + "|layername=towns", "towns", "ogr")
        self.assertTrue(towns.isValid())
        QgsProject.instance().addMapLayer(towns)

    def _run(self, alg_id, params, **kw):
        from cartogen_ai.core.agent.tools.processing_allowlist_tools import run_allowlisted_processing_algorithm
        result = run_allowlisted_processing_algorithm(alg_id, params, **kw)
        print(f"PLOTINFORESULT {alg_id} {'ok' if result.get('success') else 'FAILED'} {str(result)[:240]}")
        return result

    def test_every_chart_writes_a_complete_temporary_page(self):
        for alg_id, params in PLOTS.items():
            with self.subTest(alg_id):
                result = self._run(alg_id, params)
                self.assertTrue(result.get("success"), result)
                path = next(iter((result.get("report_files") or {}).values()), None)
                self.assertTrue(path and os.path.isfile(path), result)
                self.assertGreater(os.path.getsize(path), 1000)
                with open(path, encoding="utf-8", errors="replace") as fh:
                    self.assertIn("plotly", fh.read(200000).lower())

    def test_a_chart_path_the_caller_supplies_is_ignored(self):
        evil = os.path.join(self.folder, "evil_chart.html")
        result = self._run("qgis:barplot", {**PLOTS["qgis:barplot"], "OUTPUT": evil})
        self.assertTrue(result.get("success"), result)
        self.assertFalse(os.path.exists(evil))

    def test_raster_information_names_the_driver_and_the_size(self):
        result = self._run("gdal:gdalinfo", {"INPUT": "dem"})
        self.assertTrue(result.get("success"), result)
        self.assertIn("Driver: GTiff", result["report_text"])
        self.assertIn("Size is 40, 40", result["report_text"])

    def test_vector_information_in_text_and_in_json(self):
        text = self._run("gdal:ogrinfo", {"INPUT": "towns"})
        self.assertTrue(text.get("success"), text)
        self.assertIn("GPKG", text["report_text"])
        as_json = self._run("gdal:ogrinfojson", {"INPUT": "towns"})
        self.assertTrue(as_json.get("success"), as_json)
        self.assertIn('"driverShortName"', as_json["report_text"])
        self.assertLessEqual(len(as_json["report_text"]), 4000)

    def test_record_whether_the_elevation_profile_image_can_run(self):
        # not asserted, and NOT through the generic tool (the algorithm is not approved, so that tool would refuse it): the answer decides whether it is built
        import processing
        out = os.path.join(self.folder, "profile.png")
        try:
            result = processing.run("native:generateelevationprofileimage", {"CURVE": "LineString(0.2 0.2, 3.8 3.8)", "MAP_LAYERS": ["dem"], "TERRAIN_LAYER": "dem",
                                                                              "WIDTH": 400, "HEIGHT": 300, "OUTPUT": out})
            print(f"ELEVPROFILE ok {sorted(result)} file={os.path.isfile(out)} bytes={os.path.getsize(out) if os.path.isfile(out) else 0}")
        except Exception as e:  # a probe: any failure is the answer
            print(f"ELEVPROFILE FAILED {type(e).__name__}: {str(e)[:400]}")

if __name__ == "__main__":
    unittest.main()
