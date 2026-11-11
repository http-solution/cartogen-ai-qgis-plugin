"""Live run of calculate_health_rates (PLAN-023 R2-4) on real QGIS layers. Known answers: areas with cases 10, 20, 30 and populations 1000, 2000, 3000 each have 1,000 per 100,000 and relative risk 1; an area with 4 cases is flagged
'cases below 5' and has an empty value_shown; method 'smr' without an expected field is refused. Written without a QGIS install: CI's first run is its first execution."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


def _boot():
    from tests.test_chat_widget_live import _boot_qgis
    _boot_qgis()


def _areas(name, cases, pops, expected=None, geometry=True, case_type="integer"):
    head = "Polygon?crs=EPSG:3857&" if geometry else "None?"
    layer = QgsVectorLayer(f"{head}field=cases:{case_type}&field=pop:double&field=expd:double&field=label:string", name, "memory")
    feats = []
    for i, (c, p) in enumerate(zip(cases, pops, strict=True)):
        f = QgsFeature(layer.fields())
        if geometry:
            f.setGeometry(QgsGeometry.fromWkt(f"POLYGON(({i} 0,{i + 1} 0,{i + 1} 1,{i} 1,{i} 0))"))
        f.setAttributes([c, p, None if expected is None else expected[i], f"a{i}"])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    QgsProject.instance().addMapLayer(layer)
    return layer


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestHealthRatesTool(unittest.TestCase):
    def setUp(self):
        _boot()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _run(self, *args, **kwargs):
        from cartogen_ai.core.agent.tools.health_rates_tool import calculate_health_rates
        return calculate_health_rates(*args, **kwargs)

    def test_equal_rates_give_1000_per_100000_and_relative_risk_one(self):
        source = _areas("a", [10, 20, 30], [1000, 2000, 3000])
        before = [(f.id(), f["cases"], f["label"]) for f in source.getFeatures()]
        result = self._run("a", "cases", "pop")
        self.assertTrue(result.get("success"), result)
        self.assertEqual(result["output_layer"], "a_rates")
        self.assertEqual(result["overall_rate"], 1000.0)
        out = QgsProject.instance().mapLayersByName("a_rates")[0]
        self.assertEqual(out.featureCount(), 3)
        for f in out.getFeatures():
            self.assertEqual(f["rate"], 1000.0)
            self.assertEqual(f["rel_risk"], 1.0)
            self.assertEqual(f["value"], 1000.0)
            self.assertEqual(f["value_shown"], 1000.0)
            self.assertFalse(f["small_number"])
        self.assertEqual([(f.id(), f["cases"], f["label"]) for f in source.getFeatures()], before)
        self.assertFalse(source.isEditable())

    def test_an_area_with_four_cases_is_flagged_and_its_value_is_not_shown(self):
        _areas("a", [4, 50, 60], [1000, 5000, 6000])
        result = self._run("a", "cases", "pop")
        self.assertTrue(result.get("success"), result)
        self.assertEqual(result["flagged_small_numbers"], 1)
        self.assertEqual(result["shown"], 2)
        out = QgsProject.instance().mapLayersByName("a_rates")[0]
        rows = sorted(out.getFeatures(), key=lambda f: f["src_id"])
        self.assertEqual(rows[0]["small_number"], "cases below 5")
        self.assertTrue(rows[0]["value_shown"] is None or str(rows[0]["value_shown"]) == "NULL")      # a QGIS NULL compares equal to its string form
        self.assertEqual(rows[0]["value"], 400.0)
        self.assertFalse(rows[1]["small_number"])

    def test_a_population_floor_flags_small_populations(self):
        _areas("a", [50, 60], [800, 6000])
        result = self._run("a", "cases", "pop", min_population=1000)
        self.assertEqual(result["flagged_small_numbers"], 1)

    def test_smr_uses_the_expected_field(self):
        _areas("a", [30, 10], [1000, 1000], expected=[20.0, 20.0])
        result = self._run("a", "cases", "pop", method="smr", expected_field="expd")
        self.assertTrue(result.get("success"), result)
        out = QgsProject.instance().mapLayersByName("a_rates")[0]
        rows = sorted(out.getFeatures(), key=lambda f: f["src_id"])
        self.assertEqual([r["smr"] for r in rows], [1.5, 0.5])
        self.assertEqual([r["value"] for r in rows], [1.5, 0.5])

    def test_eb_smooths_and_says_when_everything_collapses_to_the_overall_rate(self):
        _areas("a", [10, 40], [1000, 4000])
        result = self._run("a", "cases", "pop", method="eb")
        self.assertTrue(result.get("success"), result)
        self.assertIn("overall rate", result["smoothing"])

    def test_a_table_without_geometry_works(self):
        _areas("t", [10, 20, 30], [1000, 2000, 3000], geometry=False)
        result = self._run("t", "cases", "pop")
        self.assertTrue(result.get("success"), result)
        self.assertEqual(QgsProject.instance().mapLayersByName("t_rates")[0].featureCount(), 3)

    def test_refusals_name_the_cause(self):
        _areas("a", [10, 20, 30], [1000, 2000, 3000])
        _areas("frac", [2.5, 5, 6], [100, 100, 100], case_type="double")       # an integer field cannot hold 2.5 (CI run 43088474111 truncated it to 2, so nothing was refused)
        _areas("zero", [5, 5, 6], [0, 100, 100])
        self.assertIn("not found", self._run("nope", "cases", "pop")["error"])
        self.assertIn("not found", self._run("a", "nope", "pop")["error"])
        self.assertIn("not numeric", self._run("a", "label", "pop")["error"])
        self.assertIn("does not invent", self._run("a", "cases", "pop", method="smr")["error"])
        self.assertIn("Unknown method", self._run("a", "cases", "pop", method="median")["error"])
        self.assertIn("whole-number", self._run("frac", "cases", "pop")["error"])
        self.assertIn("population above zero", self._run("zero", "cases", "pop")["error"])
        self.assertIn("per", self._run("a", "cases", "pop", per=0)["error"])


if __name__ == "__main__":
    unittest.main()
