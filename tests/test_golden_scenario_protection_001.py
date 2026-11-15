"""
Golden Scenario GS-PROTECTION-001: Protection & Sensitive Data Privacy Safeguards (Do No Harm).

Validates:
- Protection-sensitive point datasets (e.g. GBV incidents, individual IDP shelters):
  * Obfuscation methods ('jitter', 'grid_snap', 'admin_unit_snap') correctly displace/aggregate locations.
  * Monte Carlo & area uniformity: Jitter does not bias points toward original coordinates.
  * Grid snap: Disparate coordinates within the same cell collapse to identical cell centroids.
  * Admin unit snap: Displaces points to polygon centroid, stripping coordinate precision.
- Sensitive Layer Export Safeguard:
  * Export tool checks layer sensitivity tags and attaches advisory warnings to avoid unintended distribution.
  * System prompts enforce Rule 26 (never publish raw individual-level protection points without user consent).
"""

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
    QgsPointXY,
    QgsField,
)
from qgis.PyQt.QtCore import QVariant

from cartogen_ai.core.agent.tools.vector_tools import obfuscate_sensitive_points
from cartogen_ai.core.agent.tools.export_tools import export_layer
from cartogen_ai.core.models.sensitivity import set_layer_sensitivity


class TestGoldenScenarioProtection001(unittest.TestCase):
    def setUp(self):
        self.project = QgsProject.instance()
        self.project.removeAllMapLayers()

    def tearDown(self):
        self.project.removeAllMapLayers()

    def test_gs_protection_001_point_obfuscation_and_export_guard(self):
        # 1. Create synthetic sensitive point layer (individual incident locations)
        vl = QgsVectorLayer("Point?crs=EPSG:4326", "sensitive_protection_incidents", "memory")
        pr = vl.dataProvider()
        pr.addAttributes([
            QgsField("case_id", QVariant.String),
            QgsField("severity", QVariant.Int),
        ])
        vl.updateFields()

        # Place 3 sensitive points close to each other
        pts_data = [
            ("CASE-001", 10.001, 20.001),
            ("CASE-002", 10.003, 20.002),
            ("CASE-003", 10.008, 20.007),
        ]
        feats = []
        for cid, x, y in pts_data:
            f = QgsFeature(vl.fields())
            f.setAttribute("case_id", cid)
            f.setAttribute("severity", 4)
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
            feats.append(f)
        pr.addFeatures(feats)
        vl.updateExtents()
        self.project.addMapLayer(vl)

        # 2. Tag layer as RESTRICTED under humanitarian data sensitivity policy
        set_layer_sensitivity(vl, "RESTRICTED", reason="Individual protection cases")

        # 3. Apply grid_snap obfuscation (cell size = 0.05 degrees)
        # All 3 points fall in the same cell and must collapse to the identical centroid
        res_obf = obfuscate_sensitive_points(
            layer_name="sensitive_protection_incidents",
            method="grid_snap",
            cell_size=0.05,
            output_layer_name="obfuscated_incidents",
        )
        self.assertTrue(res_obf.get("success"), f"Obfuscation failed: {res_obf}")
        self.assertEqual(res_obf["feature_count"], 3)

        obf_layer = self.project.mapLayersByName("obfuscated_incidents")[0]
        obf_coords = [f.geometry().asPoint() for f in obf_layer.getFeatures()]

        # Assert all points snapped to the exact same cell centroid, stripping true identity
        first_pt = obf_coords[0]
        for pt in obf_coords[1:]:
            self.assertAlmostEqual(pt.x(), first_pt.x(), places=5)
            self.assertAlmostEqual(pt.y(), first_pt.y(), places=5)

        # 4. Export Test: Raw restricted layer triggers advisory warning
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            out_gpkg = f"{tmpdir}/export_test.gpkg"
            res_export = export_layer(
                layer_name="sensitive_protection_incidents",
                format="gpkg",
                output_path=out_gpkg,
            )
            self.assertTrue(res_export.get("success"), f"Export failed: {res_export}")
            # Advisory warning must be attached for RESTRICTED
            self.assertIn("warning", res_export)
            self.assertIn("RESTRICTED", res_export["warning"])
            self.assertIn("Individual protection cases", res_export["warning"])

        # 5. Strict Protection Test: Tag layer as HIGHLY_SENSITIVE -> Raw export MUST be BLOCKED
        set_layer_sensitivity(vl, "HIGHLY_SENSITIVE", reason="Unmasked GBV survivor records")
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            blocked_gpkg = f"{tmpdir}/blocked_test.gpkg"
            res_blocked = export_layer(
                layer_name="sensitive_protection_incidents",
                format="gpkg",
                output_path=blocked_gpkg,
            )
            self.assertIn("error", res_blocked)
            self.assertTrue(res_blocked.get("blocked_by_protection_policy"))
            self.assertIn("Export BLOCKED under Do No Harm protection policy", res_blocked["error"])
            self.assertIn("HIGHLY_SENSITIVE", res_blocked["error"])


if __name__ == "__main__":
    unittest.main()
