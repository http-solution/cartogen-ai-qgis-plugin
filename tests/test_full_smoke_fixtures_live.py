"""Live check of the inputs of smoke rows C20 to C27 (PLAN-056): the generated files are written to a folder, loaded by real QGIS exactly as the rows tell a person to load them, and the real tools are run on them. Every
number asserted here is the number quoted in the row (tests/test_r2_smoke_inputs.py recomputes the same numbers offline from the plugin's pure code). Written without a QGIS install: CI's first run is its first execution."""
import sys
import tempfile
import unittest
from pathlib import Path

try:
    from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


def _boot():
    from tests.test_chat_widget_live import _boot_qgis
    _boot_qgis()


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestTheShippedInputsInRealQgis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _boot()
        import make_full_smoke_fixtures as fx
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        fx.write_all(cls.tmp.name)

    def setUp(self):
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def vector(self, file, name):
        layer = QgsVectorLayer(str(Path(self.tmp.name) / file), name, "ogr")
        self.assertTrue(layer.isValid(), file)
        QgsProject.instance().addMapLayer(layer)
        return layer

    def names_by_id(self, layer):
        return {f.id(): f["name"] for f in layer.getFeatures()}

    def test_the_district_layer_loads_projected_with_its_fields(self):
        layer = self.vector("smoke_districts_cases.geojson", "smoke_districts_cases")
        self.assertEqual(layer.crs().authid(), "EPSG:32636")
        self.assertEqual(layer.featureCount(), 100)
        self.assertEqual([f.name() for f in layer.fields()][:6], ["id", "name", "cases", "population", "expected", "burglaries"])
        self.assertEqual(sum(f["cases"] for f in layer.getFeatures()), 707)

    def test_row_c21_morans_i(self):
        from cartogen_ai.core.agent.tools.spatial_stats_tool import calculate_spatial_autocorrelation as moran
        self.vector("smoke_checker4.geojson", "smoke_checker4")
        a = moran("smoke_checker4", "v", weights="rook", permutations=999)
        self.assertEqual((a["moran_i"], a["expected_i"], a["features"], a["mean_neighbours"], a["islands"]), (-1.0, -0.0667, 16, 3.0, 0))
        self.assertIn("DIFFERENT", a["interpretation"])
        self.vector("smoke_districts_cases.geojson", "smoke_districts_cases")
        b = moran("smoke_districts_cases", "cases", weights="queen", permutations=999, write_local=True)
        self.assertEqual((b["moran_i"], b["expected_i"], b["mean_neighbours"], b["islands"], b["separate_groups"]), (0.3383, -0.0101, 6.84, 0, 1))
        self.assertAlmostEqual(b["z_permutation"], 6.83, delta=0.02)
        self.assertEqual(b["local_counts"], {"HH": 9, "LL": 1, "HL": 0, "LH": 4, "not significant": 86, "no neighbours": 0})
        self.assertEqual(QgsProject.instance().mapLayersByName("smoke_districts_cases_lisa")[0].featureCount(), 100)
        self.assertEqual(moran("smoke_districts_cases", "cases", weights="rook")["moran_i"], 0.4114)
        self.assertEqual(moran("smoke_districts_cases", "cases", weights="knn", k=5)["mean_neighbours"], 5.0)

    def test_row_c22_gi_star(self):
        from cartogen_ai.core.agent.tools.hotspot_tool import analyze_hotspots_gi_star as gi
        self.vector("smoke_one_high5.geojson", "smoke_one_high5")
        a = gi("smoke_one_high5", "v", weights="rook", fdr=False)
        self.assertEqual((a["hot_spots"], a["cold_spots"], a["classes"]), (5, 0, {"Hot spot 95%": 5, "Not significant": 20}))
        self.assertIn("(NOT corrected for the number of tests)", a["summary"])
        out = QgsProject.instance().mapLayersByName("smoke_one_high5_gi_star")[0]
        src = self.vector("smoke_one_high5.geojson", "reread")
        names = self.names_by_id(src)
        z = {names[f["src_id"]]: f["gi_z"] for f in out.getFeatures()}
        for cell in ("H22", "H12", "H21", "H23", "H32"):
            self.assertAlmostEqual(z[cell], 2.0, places=3, msg=cell)
        self.assertAlmostEqual(z["H00"], -0.3693, places=3)
        self.vector("smoke_districts_cases.geojson", "smoke_districts_cases")
        b = gi("smoke_districts_cases", "cases", weights="queen", fdr=True)
        self.assertEqual((b["classes"]["Hot spot 99%"], b["classes"]["Hot spot 95%"], b["classes"]["Not significant"], b["islands"]), (7, 2, 91, 0))
        self.assertIn("(false-discovery corrected)", b["summary"])
        self.assertEqual(gi("smoke_districts_cases", "cases", weights="queen", fdr=False, output_layer_name="nofdr")["classes"], {"Not significant": 87, "Hot spot 95%": 2, "Hot spot 99%": 11})

    def test_row_c23_cluster_scan(self):
        from cartogen_ai.core.agent.tools.cluster_scan_tool import detect_spatial_clusters as scan
        layer = self.vector("smoke_districts_cases.geojson", "smoke_districts_cases")
        r = scan("smoke_districts_cases", "cases", "population", monte_carlo=999, seed=1)
        self.assertTrue(r.get("success"), r)
        best = r["clusters"][0]
        self.assertEqual(self.names_by_id(layer)[best["centre_id"]], "D44")
        self.assertEqual((best["areas"], best["cases"], best["expected"], best["relative_risk"], best["llr"], best["radius"], best["p_value"]), (9, 135, 63.63, 2.386, 34.289, 1414.214, 0.001))
        self.assertEqual((len(r["clusters"]), r["significant_clusters"], r["total_cases"]), (1, 1, 707))
        small = scan("smoke_districts_cases", "cases", "population", monte_carlo=999, seed=1, max_pop_fraction=0.05, output_layer_name="capped")
        self.assertTrue(all(c["areas"] <= 5 for c in small["clusters"]))
        self.assertEqual((small["clusters"][0]["areas"], small["clusters"][0]["cases"]), (5, 75))
        self.assertEqual(scan("smoke_districts_cases", "cases", "population", monte_carlo=999, seed=1, max_pop_fraction=0.05, output_layer_name="capped2")["clusters"], small["clusters"])
        self.assertIn("not built", scan("smoke_districts_cases", "cases", "population", model="bernoulli")["error"])

    def test_row_c24_rates(self):
        from cartogen_ai.core.agent.tools.health_rates_tool import calculate_health_rates as rates
        self.vector("smoke_rates3.geojson", "smoke_rates3")
        a = rates("smoke_rates3", "cases", "population", method="smr", expected_field="expected")
        self.assertEqual((a["flagged_small_numbers"], a["overall_rate"]), (0, 1000.0))
        out = QgsProject.instance().mapLayersByName("smoke_rates3_rates")[0]
        rows = sorted(out.getFeatures(), key=lambda f: f["src_id"])
        self.assertEqual([(f["rate"], f["rel_risk"], f["smr"]) for f in rows], [(1000.0, 1.0, 1.25), (1000.0, 1.0, 0.8), (1000.0, 1.0, 1.0)])
        layer = self.vector("smoke_districts_cases.geojson", "smoke_districts_cases")
        b = rates("smoke_districts_cases", "cases", "population")
        self.assertEqual((b["overall_rate"], b["flagged_small_numbers"], b["shown"]), (707.0, 4, 96))
        names = self.names_by_id(layer)
        table = {names[f["src_id"]]: f for f in QgsProject.instance().mapLayersByName("smoke_districts_cases_rates")[0].getFeatures()}
        for n, rate in (("D00", 400.0), ("D09", 300.0), ("D90", 0.0), ("D99", 200.0)):
            self.assertEqual((table[n]["rate"], table[n]["small_number"]), (rate, "cases below 5"), n)
            self.assertTrue(table[n]["value_shown"] is None or str(table[n]["value_shown"]) == "NULL", n)
        self.assertEqual((table["D44"]["rate"], table["D44"]["rel_risk"], table["D44"]["rate_lo"], table["D44"]["rate_hi"]), (1500.0, 2.1216, 838.9264, 2474.1631))
        self.assertEqual((table["D11"]["rate"], table["D11"]["rel_risk"]), (600.0, 0.8487))
        rates("smoke_districts_cases", "cases", "population", method="eb", output_layer_name="eb")
        eb = {names[f["src_id"]]: f["value"] for f in QgsProject.instance().mapLayersByName("eb")[0].getFeatures()}
        self.assertAlmostEqual(eb["D44"], 806.563, places=3)
        self.assertEqual(rates("smoke_districts_cases", "cases", "population", min_cases=0, output_layer_name="none")["flagged_small_numbers"], 0)
        self.assertIn("does not invent", rates("smoke_districts_cases", "cases", "population", method="smr", output_layer_name="smr")["error"])

    def test_row_c25_looks(self):
        from cartogen_ai.core.agent.tools.cluster_scan_tool import detect_spatial_clusters as scan
        from cartogen_ai.core.agent.tools.health_rates_tool import calculate_health_rates as rates
        from cartogen_ai.core.agent.tools.hotspot_tool import analyze_hotspots_gi_star as gi
        from cartogen_ai.core.agent.tools.public_health_look_tool import apply_public_health_look as look
        self.vector("smoke_districts_cases.geojson", "smoke_districts_cases")
        rates("smoke_districts_cases", "cases", "population")
        scan("smoke_districts_cases", "cases", "population")
        gi("smoke_districts_cases", "cases")
        r = look("smoke_districts_cases_rates", "rate")
        self.assertEqual((len(r["classes"]), r["classes_dropped"], r["shown"], r["suppressed"], r["legend_title"]), (4, 1, 96, 4, "Rate per 100,000; suppressed where n < 5"))
        self.assertEqual([c["label"] for c in r["classes"]], ["500 to 600", "600 to 700", "700 to 800", "800 to 1,500"])
        self.assertEqual(QgsProject.instance().mapLayersByName("smoke_districts_cases_rates")[0].renderer().rootRule().children()[-1].label(), "Suppressed (n < 5)")
        self.assertTrue(look("smoke_districts_cases_scan_clusters", "cluster").get("success"))
        self.assertTrue(look("smoke_districts_cases_gi_star", "hotspot").get("success"))

    def test_row_c20_land_cover_and_change_inputs(self):
        from cartogen_ai.core.agent.tools.land_cover_look_tool import apply_land_cover_look as lc
        raster = QgsRasterLayer(str(Path(self.tmp.name) / "smoke_worldcover.asc"), "smoke_worldcover")
        self.assertTrue(raster.isValid())
        self.assertEqual((raster.width(), raster.height(), raster.crs().authid()), (40, 40, "EPSG:32636"))
        QgsProject.instance().addMapLayer(raster)
        r = lc("smoke_worldcover", "esa_worldcover")
        self.assertTrue(r.get("success"), r)
        self.assertEqual(r["unmatched_values"], ["11"])
        labels = [c["label"] for c in r["classes"]]
        self.assertEqual(labels, ["Tree cover (10)", "Grassland (30)", "Cropland (40)", "Built-up (50)", "Permanent water bodies (80)", "11 (not in the ESA WorldCover legend)"])
        self.vector("smoke_change_classes.geojson", "smoke_change_classes")
        self.assertTrue(lc("smoke_change_classes", "change_classes", field="change").get("success"))
        self.assertTrue(lc("smoke_change_classes", "change_classes", field="change_word").get("success"))
        self.assertTrue(lc("smoke_change_classes", "protected_area_hatch").get("success"))
        self.assertIn("nothing was restyled", lc("smoke_worldcover", "change_classes")["error"])

    def test_row_c27_geocoding_inputs(self):
        from cartogen_ai.core.agent.tools import system_tools
        from cartogen_ai.core.models import sensitivity
        clients = self.vector("smoke_clients.geojson", "smoke_clients")
        self.vector("smoke_clinics.geojson", "smoke_clinics")
        self.assertEqual(clients.crs().authid(), "EPSG:4326")
        sensitivity.set_layer_sensitivity(clients, "SENSITIVE", "test")
        sensitivity.set_layer_sensitivity(QgsProject.instance().mapLayersByName("smoke_clinics")[0], "PUBLIC", "test")
        seen = []
        original = system_tools._geocode_one
        system_tools._geocode_one = lambda name: seen.append(name) or {"lat": 1.0, "lon": 2.0}
        self.addCleanup(setattr, system_tools, "_geocode_one", original)
        refused = system_tools.geocode_batch(["Flat 3, 12 Example Street, Crater, Aden", "7 Sample Lane, Khormaksar, Aden"])
        self.assertEqual(refused["status"], "GEOCODING_REFUSED_PROTECTED")
        self.assertEqual(refused["layers"], ["smoke_clients"])
        self.assertIn("2 of the 2 text(s) match", refused["error"])
        self.assertEqual(system_tools.geocode_batch(["x"], source_layer="smoke_clients")["status"], "GEOCODING_REFUSED_PROTECTED")
        self.assertEqual(seen, [])
        self.assertTrue(system_tools.geocode_batch(["Aden International Airport, Aden, Yemen"], source_layer="smoke_clinics").get("success"))
        self.assertEqual(seen, ["Aden International Airport, Aden, Yemen"])


if __name__ == "__main__":
    unittest.main()
