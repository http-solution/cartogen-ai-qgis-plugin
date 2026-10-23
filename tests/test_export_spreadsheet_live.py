"""Live run of export_layers_to_spreadsheet in the QGIS image CI uses: a real .xlsx is written and read back as a layer (rows and values),
a text value that looks like a formula comes back as text, the extension is added, an existing file asks first, a raster is refused.
Written without a QGIS install: CI's first run is its first execution."""
import os
import tempfile
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsRasterLayer, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestExportLayersToSpreadsheetLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.folder = tempfile.mkdtemp()
        clinics = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string&field=beds:integer", "clinics_xl", "memory")
        features = []
        for name, beds in (("North clinic", 12), ("=1+1", 30), ("South clinic", 7)):
            f = QgsFeature(clinics.fields())
            f.setGeometry(QgsGeometry.fromWkt("POINT(10 10)"))
            f.setAttributes([name, beds])
            features.append(f)
        clinics.dataProvider().addFeatures(features)
        QgsProject.instance().addMapLayer(clinics)

    def _export(self, **kw):
        from cartogen_ai.core.agent.tools.export_tools import export_layers_to_spreadsheet
        return export_layers_to_spreadsheet(["clinics_xl"], **kw)

    def test_a_real_xlsx_is_written_and_reads_back(self):
        path = os.path.join(self.folder, "clinics.xlsx")
        result = self._export(output_path=path)
        print(f"XLSXRESULT {str(result)[:300]}")
        self.assertTrue(result.get("success"), result)
        self.assertGreater(os.path.getsize(path), 0)
        back = QgsVectorLayer(path, "back", "ogr")
        self.assertTrue(back.isValid(), path)
        self.assertEqual(back.featureCount(), 3)
        self.assertEqual(sorted(f["beds"] for f in back.getFeatures()), [7, 12, 30])

    def test_a_formula_looking_name_comes_back_as_text(self):
        path = os.path.join(self.folder, "formula.xlsx")
        self.assertTrue(self._export(output_path=path).get("success"))
        back = QgsVectorLayer(path, "back", "ogr")
        self.assertIn("=1+1", [f["name"] for f in back.getFeatures()])

    def test_a_missing_extension_becomes_xlsx(self):
        result = self._export(output_path=os.path.join(self.folder, "plain"))
        self.assertTrue(result.get("success"), result)
        self.assertTrue(result["output_path"].endswith(".xlsx"))

    def test_an_existing_file_asks_before_it_is_replaced(self):
        path = os.path.join(self.folder, "existing.xlsx")
        with open(path, "w") as fh:
            fh.write("not ours")
        result = self._export(output_path=path)
        self.assertEqual(result.get("status"), "PREVIEW_REQUIRED", result)
        with open(path) as fh:
            self.assertEqual(fh.read(), "not ours")

    def test_a_raster_is_refused(self):
        from tests._geometry_probe import _make_rasters
        from cartogen_ai.core.agent.tools.export_tools import export_layers_to_spreadsheet
        for name, raster_path in _make_rasters(self.folder).items():
            QgsProject.instance().addMapLayer(QgsRasterLayer(raster_path, name))
            result = export_layers_to_spreadsheet([name], output_path=os.path.join(self.folder, "r.xlsx"))
            self.assertIn("not a vector layer", result["error"])
            break


if __name__ == "__main__":
    unittest.main()
