# -*- coding: utf-8 -*-
"""
Golden Scenario GS-COD-001: Common Operational Datasets (COD-AB) P-Code Validation & Hierarchy Integrity.

Validates:
- P-code uniqueness verification across administrative units (detects duplicate P-codes that corrupt joins)
- Parent-Child P-code hierarchy consistency (checks that Admin-2 P-codes e.g. 'YE1201' properly match Admin-1 parent 'YE12')
- Rejection of invalid codes and detection of malformed hierarchies before any analytical join is performed.
"""

import unittest
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsRectangle,
    QgsField,
)
from qgis.PyQt.QtCore import QVariant

from cartogen_ai.core.agent.tools.pcode_validation_tools import (
    check_pcode_uniqueness,
    check_pcode_hierarchy,
)


class TestGoldenScenarioCod001(unittest.TestCase):
    def setUp(self):
        self.project = QgsProject.instance()
        self.project.removeAllMapLayers()

    def tearDown(self):
        self.project.removeAllMapLayers()

    def test_gs_cod_001_pcode_uniqueness_and_hierarchy(self):
        # 1. Create layer with a duplicate P-code and an invalid parent-child hierarchy
        vl = QgsVectorLayer("Polygon?crs=EPSG:4326", "cod_boundaries", "memory")
        pr = vl.dataProvider()
        pr.addAttributes([
            QgsField("adm2_pcode", QVariant.String),
            QgsField("adm1_pcode", QVariant.String),
            QgsField("adm2_en", QVariant.String),
        ])
        vl.updateFields()

        records = [
            # Valid feature: ADM2 'YE1201' correctly belongs to parent 'YE12'
            ("YE1201", "YE12", "District 1"),
            # Valid feature: ADM2 'YE1202' correctly belongs to parent 'YE12'
            ("YE1202", "YE12", "District 2"),
            # Invalid feature: ADM2 'YE1301' has wrong parent 'YE12' (prefix mismatch)
            ("YE1301", "YE12", "District 3"),
            # Duplicate feature: ADM2 'YE1201' duplicated!
            ("YE1201", "YE12", "District 1 Duplicate"),
        ]

        feats = []
        for i, (a2, a1, name) in enumerate(records):
            f = QgsFeature(vl.fields())
            f.setAttribute("adm2_pcode", a2)
            f.setAttribute("adm1_pcode", a1)
            f.setAttribute("adm2_en", name)
            f.setGeometry(QgsGeometry.fromRect(QgsRectangle(i * 1.0, 0, (i + 1) * 1.0, 1)))
            feats.append(f)
        pr.addFeatures(feats)
        vl.updateExtents()
        self.project.addMapLayer(vl)

        # 2. Test P-code uniqueness check
        res_unique = check_pcode_uniqueness("cod_boundaries", pcode_field="adm2_pcode")
        self.assertTrue(res_unique.get("success"))
        # Must detect that ADM2_PCODE is NOT unique and report the duplicate 'YE1201'
        self.assertFalse(res_unique["passed"])
        self.assertIn("YE1201", res_unique["duplicate_pcodes"])
        self.assertEqual(len(res_unique["duplicate_pcodes"]["YE1201"]), 2)

        # 3. Test P-code hierarchy check
        res_hier = check_pcode_hierarchy("cod_boundaries", child_pcode_field="adm2_pcode", parent_pcode_field="adm1_pcode")
        self.assertTrue(res_hier.get("success"))
        # Must detect that YE1301 does not match parent YE12
        self.assertFalse(res_hier["passed"])
        mismatches = res_hier["mismatches"]
        self.assertTrue(any(v["child_pcode"] == "YE1301" for v in mismatches))


if __name__ == "__main__":
    from qgis.core import QgsApplication
    qgs = QgsApplication([], False)
    qgs.initQgis()
    try:
        unittest.main()
    finally:
        qgs.exitQgis()
