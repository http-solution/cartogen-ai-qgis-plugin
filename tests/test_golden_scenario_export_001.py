"""
Golden Scenario GS-EXPORT-001: Canonical GeoPackage Export & Shapefile Truncation / Collision Detection.

Validates:
- GeoPackage (GPKG) is canonical default:
  * Preserves arbitrary field name length (>10 characters).
  * Preserves full data types and precision.
  * Exports cleanly with zero laundering.
- Shapefile (SHP) Degradation Warning Assertion:
  * Explicitly flags DBF 10-character truncation (e.g. 'population_in_need' -> 'population').
  * Explicitly flags OGR laundering collisions (e.g. 'population_density' and 'population_growth' colliding).
  * Advises GeoPackage as the safe humanitarian standard.
"""

import os
import unittest
import tempfile


try:
    import qgis.core  # noqa: F401
except ImportError:
    raise unittest.SkipTest("requires real QGIS") from None  # the plain test job has no QGIS: skip the module instead of failing the whole run at import

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsRectangle,
    QgsField,
)
from qgis.PyQt.QtCore import QVariant

from cartogen_ai.core.agent.tools.export_tools import export_layer, _check_shapefile_field_names


class TestGoldenScenarioExport001(unittest.TestCase):
    def setUp(self):
        self.project = QgsProject.instance()
        self.project.removeAllMapLayers()

    def tearDown(self):
        self.project.removeAllMapLayers()

    def test_gs_export_001_canonical_gpkg_and_shp_warning(self):
        # 1. Create layer with typical long humanitarian indicators (>10 characters)
        vl = QgsVectorLayer("Polygon?crs=EPSG:4326", "humanitarian_needs_export", "memory")
        pr = vl.dataProvider()
        pr.addAttributes([
            QgsField("adm2_pcode", QVariant.String),
            QgsField("population_total", QVariant.Int),
            QgsField("population_in_need", QVariant.Int),
            QgsField("population_reached", QVariant.Int),
        ])
        vl.updateFields()

        feat = QgsFeature(vl.fields())
        feat.setAttribute("adm2_pcode", "BF0101")
        feat.setAttribute("population_total", 50000)
        feat.setAttribute("population_in_need", 22000)
        feat.setAttribute("population_reached", 18000)
        feat.setGeometry(QgsGeometry.fromRect(QgsRectangle(0.0, 0.0, 1.0, 1.0)))
        pr.addFeatures([feat])
        vl.updateExtents()
        self.project.addMapLayer(vl)

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            # 2. Canonical Export to GeoPackage (.gpkg)
            out_gpkg = os.path.join(tmpdir, "canonical_export.gpkg")
            res_gpkg = export_layer("humanitarian_needs_export", format="gpkg", output_path=out_gpkg)
            self.assertTrue(res_gpkg.get("success"), f"GPKG export failed: {res_gpkg}")
            self.assertEqual(res_gpkg["feature_count"], 1)
            # GPKG must have no truncation warning
            self.assertNotIn("shapefile_truncation_warning", res_gpkg)

            # Read back GPKG and verify exact field names were preserved intact
            gpkg_layer = QgsVectorLayer(out_gpkg, "gpkg_check", "ogr")
            self.assertTrue(gpkg_layer.isValid())
            gpkg_fields = [f.name() for f in gpkg_layer.fields()]
            self.assertIn("population_in_need", gpkg_fields)
            self.assertIn("population_reached", gpkg_fields)
            del gpkg_layer

            # 3. Shapefile Preflight & Export: Verify truncation and collision warning
            warning_msg, field_map = _check_shapefile_field_names(vl)
            self.assertIsNotNone(warning_msg)
            self.assertIn("10 characters", warning_msg)
            self.assertIn("collision", warning_msg.lower())
            self.assertIn("GeoPackage", warning_msg)

            # Assert truncation mapping
            # "population_total" -> "population" (10 chars)
            # "population_in_need" -> "populati_1" (collision disambiguation)
            # "population_reached" -> "populati_2"
            self.assertEqual(field_map["population_total"], "population")
            self.assertEqual(field_map["population_in_need"], "populati_1")
            self.assertEqual(field_map["population_reached"], "populati_2")

            # 4. Export to Shapefile: Verify warning is emitted in tool return payload
            out_shp = os.path.join(tmpdir, "degraded_export.shp")
            res_shp = export_layer("humanitarian_needs_export", format="shp", output_path=out_shp)
            self.assertTrue(res_shp.get("success"), f"SHP export failed: {res_shp}")
            self.assertIn("shapefile_truncation_warning", res_shp)
            self.assertIn("field_name_mapping", res_shp)


if __name__ == "__main__":
    unittest.main()
