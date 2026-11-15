"""
Golden Scenario GS-3W-001: Operational Presence & Severity Gap Analysis.

Validates:
- High-severity district filtering (Classes 4 and 5)
- P-code / Admin join against 3W presence table
- Correct categorization: 'covered' vs 'gap' (low presence) vs 'unmatched' (missing from 3W table)
- Prevention of false-positive "Zero Presence" gaps when an admin unit is simply missing from the 3W dataset.
"""

import os
import unittest
import tempfile
import csv


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

from cartogen_ai.core.agent.tools.analysis_tools import calculate_presence_gap


class TestGoldenScenario3W001(unittest.TestCase):
    def setUp(self):
        self.project = QgsProject.instance()
        self.project.removeAllMapLayers()

    def tearDown(self):
        self.project.removeAllMapLayers()

    def test_gs_3w_001_presence_gap_integrity(self):
        """
        Scenario:
        5 Districts:
          - Dist_A (PCode: ADM01): severity=5 (High) -> in 3W with 3 orgs -> 'covered'
          - Dist_B (PCode: ADM02): severity=4 (High) -> in 3W with 0 orgs (or < threshold) -> 'gap'
          - Dist_C (PCode: ADM03): severity=5 (High) -> NOT in 3W table at all -> 'unmatched'
          - Dist_D (PCode: ADM04): severity=2 (Low)  -> in 3W with 1 org -> NOT high severity, not classified
          - Dist_E (PCode: ADM05): severity=1 (Low)  -> in 3W with 0 org -> NOT high severity, not classified
        """
        vl = QgsVectorLayer("Polygon?crs=EPSG:4326", "districts", "memory")
        pr = vl.dataProvider()
        pr.addAttributes([
            QgsField("adm_pcode", QVariant.String),
            QgsField("need_index", QVariant.Double),
        ])
        vl.updateFields()

        # Dist_A: need 100 -> score 1.0 (Class 5)
        # Dist_B: need 80  -> score 0.77 (Class 4)
        # Dist_C: need 95  -> score 0.94 (Class 5)
        # Dist_D: need 30  -> score 0.20 (Class 2)
        # Dist_E: need 12  -> score 0.00 (Class 1)
        data = [
            ("ADM01", 100.0),
            ("ADM02", 80.0),
            ("ADM03", 95.0),
            ("ADM04", 30.0),
            ("ADM05", 12.0),
        ]
        feats = []
        for i, (pcode, val) in enumerate(data):
            f = QgsFeature(vl.fields())
            f.setAttribute("adm_pcode", pcode)
            f.setAttribute("need_index", val)
            f.setGeometry(QgsGeometry.fromRect(QgsRectangle(i, 0, i + 1, 1)))
            feats.append(f)
        pr.addFeatures(feats)
        vl.updateExtents()
        self.project.addMapLayer(vl)

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            csv_path = os.path.join(tmpdir, "3w_data.csv")
            with open(csv_path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow(["admin_pcode", "organization", "cluster"])
                # ADM01 has 3 orgs -> covered (>= 2)
                writer.writerow(["ADM01", "UNICEF", "WASH"])
                writer.writerow(["ADM01", "OXFAM", "WASH"])
                writer.writerow(["ADM01", "ICRC", "HEALTH"])
                # ADM02 has 1 org -> gap (< 2 threshold)
                writer.writerow(["ADM02", "LOCAL_NGO", "HEALTH"])
                # ADM04 has 1 org (low severity)
                writer.writerow(["ADM04", "WFP", "FSAC"])
                # ADM03 is completely absent from 3W table -> unmatched

            res = calculate_presence_gap(
                layer_name="districts",
                indicator_fields=["need_index"],
                unit_name_field="adm_pcode",
                presence_file_path=csv_path,
                presence_admin_field="admin_pcode",
                presence_org_field="organization",
                high_severity_classes=[4, 5],
                low_presence_threshold=2
            )

            self.assertTrue(res.get("success"), f"Failed: {res}")

            # Verify classification buckets
            # ADM01 -> covered
            covered_units = [u["unit"] for u in res["covered_high_severity_units"]]
            self.assertIn("ADM01", covered_units)
            self.assertEqual(res["covered_high_severity_units_total"], 1)

            # ADM03 -> unmatched (NOT in 3W table)
            unmatched_units = [u["unit"] for u in res["unmatched_high_severity_units"]]
            self.assertIn("ADM03", unmatched_units)
            self.assertEqual(res["unmatched_high_severity_units_total"], 1)

            # ADM02 -> gap (1 org < 2 threshold)
            gap_units = [u["unit"] for u in res["presence_gap_units"]]
            self.assertIn("ADM02", gap_units)
            self.assertEqual(res["presence_gap_units_total"], 1)

            # Dist_D and Dist_E should NOT be in any high severity bucket
            all_high = covered_units + unmatched_units + [u["unit"] for u in res["presence_gap_units"]]
            self.assertNotIn("ADM04", all_high)
            self.assertNotIn("ADM05", all_high)


if __name__ == "__main__":
    from qgis.core import QgsApplication
    qgs = QgsApplication([], False)
    qgs.initQgis()
    try:
        unittest.main()
    finally:
        qgs.exitQgis()
