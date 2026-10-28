"""Live QGIS: a district whose raster value DROPPED is scored as the most damaged, not the least (1.18.3 hand test D7, 2026-10-26: the
zonal mean of the signed change put the district that lost 70 lowest, so unchanged districts scored 1 and the damaged one 0). Written
without a local QGIS: CI's first run is its first execution."""
import os
import tempfile
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsRasterLayer, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


def _asc(path, fn):
    cols = rows = 20
    lines = [f"ncols {cols}", f"nrows {rows}", "xllcorner 0", "yllcorner 0", "cellsize 0.01", "NODATA_value -9999"]
    lines.extend(" ".join(f"{fn(c, rows - 1 - r):.1f}" for c in range(cols)) for r in range(rows))
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(path[:-4] + ".prj", "w") as fh:
        fh.write('GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],'
                 'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]\n')


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestDamageDirection(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.tmp = tempfile.mkdtemp()
        before, after = os.path.join(self.tmp, "before.asc"), os.path.join(self.tmp, "after.asc")
        _asc(before, lambda c, r: 100.0)
        _asc(after, lambda c, r: 30.0 if c >= 10 else 100.0)   # the east half loses 70
        for path, name in ((before, "before"), (after, "after")):
            layer = QgsRasterLayer(path, name)
            self.assertTrue(layer.isValid())
            QgsProject.instance().addMapLayer(layer)
        admin = QgsVectorLayer("Polygon?crs=EPSG:4326&field=name:string", "admin", "memory")
        for name, wkt in (("west", "POLYGON((0 0,0.1 0,0.1 0.2,0 0.2,0 0))"), ("east", "POLYGON((0.1 0,0.2 0,0.2 0.2,0.1 0.2,0.1 0))")):
            f = QgsFeature(admin.fields())
            f.setGeometry(QgsGeometry.fromWkt(wkt))
            f.setAttributes([name])
            admin.dataProvider().addFeatures([f])
        QgsProject.instance().addMapLayer(admin)
        foot = QgsVectorLayer("Polygon?crs=EPSG:4326&field=id:integer", "footprints", "memory")
        f = QgsFeature(foot.fields())
        f.setGeometry(QgsGeometry.fromWkt("POLYGON((0.15 0.1,0.151 0.1,0.151 0.101,0.15 0.101,0.15 0.1))"))
        f.setAttributes([1])
        foot.dataProvider().addFeatures([f])
        QgsProject.instance().addMapLayer(foot)

    def test_the_district_that_lost_value_is_the_most_severe(self):
        from cartogen_ai.core.agent.tools.analysis_tools import calculate_damage_exposure_severity
        res = calculate_damage_exposure_severity("admin", "name", "before", "after", "footprints", output_field="damage")
        if res.get("status") == "PREVIEW_REQUIRED":
            res = calculate_damage_exposure_severity("admin", "name", "before", "after", "footprints", output_field="damage", confirmed=True)
        self.assertTrue(res.get("success"), res)
        by_unit = {u["unit"]: u for u in res["unit_results"]}
        self.assertGreater(by_unit["east"]["severity_score"], by_unit["west"]["severity_score"], res)
        admin = QgsProject.instance().mapLayersByName("admin")[0]
        written = {f["name"]: f["damage"] for f in admin.getFeatures()}
        self.assertGreater(written["east"], written["west"])

    def test_a_second_run_does_not_read_the_first_runs_stale_field(self):
        # QGIS names the second run's column chg_mean_2; the old code kept reading chg_mean (the signed 1.18.3 values after an upgrade).
        from cartogen_ai.core.agent.tools.analysis_tools import calculate_damage_exposure_severity
        admin = QgsProject.instance().mapLayersByName("admin")[0]
        from qgis.core import QgsField
        from qgis.PyQt.QtCore import QVariant
        admin.dataProvider().addAttributes([QgsField("chg_mean", QVariant.Double)])
        admin.updateFields()
        admin.startEditing()
        for f in admin.getFeatures():
            admin.changeAttributeValue(f.id(), admin.fields().indexOf("chg_mean"), -70.0 if f["name"] == "west" else 0.0)  # stale and inverted
        admin.commitChanges()
        res = calculate_damage_exposure_severity("admin", "name", "before", "after", "footprints")
        self.assertTrue(res.get("success"), res)
        by_unit = {u["unit"]: u for u in res["unit_results"]}
        self.assertGreater(by_unit["east"]["severity_score"], by_unit["west"]["severity_score"], res)

    def test_the_working_zonal_columns_are_removed_but_the_users_own_column_is_kept(self):
        # DEF-5: chg_mean / chg2_mean used to stay on the admin layer after every run. Only columns this run created may go: a column the user
        # already had under the same name (here chg_mean) stays.
        from cartogen_ai.core.agent.tools.analysis_tools import calculate_damage_exposure_severity
        from qgis.core import QgsField
        from qgis.PyQt.QtCore import QVariant
        admin = QgsProject.instance().mapLayersByName("admin")[0]
        admin.dataProvider().addAttributes([QgsField("chg_mean", QVariant.Double)])
        admin.updateFields()
        res = calculate_damage_exposure_severity("admin", "name", "before", "after", "footprints")
        self.assertTrue(res.get("success"), res)
        names = [f.name() for f in admin.fields()]
        self.assertIn("chg_mean", names, "the user's own column must stay")
        self.assertNotIn("chg2_mean", names, names)
        self.assertEqual(res.get("temporary_fields_removed"), ["chg2_mean"], res)

    def test_a_first_run_leaves_no_zonal_columns_behind(self):
        from cartogen_ai.core.agent.tools.analysis_tools import calculate_damage_exposure_severity
        res = calculate_damage_exposure_severity("admin", "name", "before", "after", "footprints")
        self.assertTrue(res.get("success"), res)
        admin = QgsProject.instance().mapLayersByName("admin")[0]
        self.assertEqual([f.name() for f in admin.fields()], ["name"])


if __name__ == "__main__":
    unittest.main()
