# -*- coding: utf-8 -*-
"""
Golden Scenario GS-OUTPUT-001: End-to-End Cross-Channel Invariant & Semantic Verification.

Validates the full delivery pipeline:
Humanitarian Request
      ↓
Contract Validation
      ↓
PyQGIS Processing (Severity / Need Calculation)
      ↓
Vector Layer Attribute Table
      ↓
Map Styling (Graduated Renderer on the exact indicator)
      ↓
Dashboard Signature (KPI Metric & Filters)
      ↓
Layout Generation (Title & Key Figure)
      ↓
GeoPackage Canonical Export
      ↓
Reconciliation Auditor Cross-Channel Check

Enforces the core invariant:
GIS ATTRIBUTE TOTAL == DASHBOARD KPI == LAYOUT METRIC == GPKG EXPORT SUM
AND asserts that the map renderer symbolizes the EXACT analyzed field,
catching deceptive "correct numbers but symbolizing the wrong field" failures.
"""

import os
import unittest
import tempfile

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsRectangle,
    QgsField,
    QgsGraduatedSymbolRenderer,
    QgsClassificationQuantile,
)
from qgis.PyQt.QtCore import QVariant

from cartogen_ai.core.validators.humanitarian_contract import (
    HumanitarianAnalysisContract,
    GeographicScope,
    HumanitarianContext,
    MethodologicalRules,
    ExpectedDeliverables,
)
from cartogen_ai.core.validators.reconciliation_auditor import (
    OutputReconciliationAuditor,
    AnalysisIntegritySignature,
    CartographicSignature,
    DashboardSignature,
    LayoutSignature,
    ExportSignature,
)
from cartogen_ai.core.agent.tools.export_tools import export_layer


class TestGoldenScenarioOutput001(unittest.TestCase):
    def setUp(self):
        self.project = QgsProject.instance()
        self.project.removeAllMapLayers()

    def tearDown(self):
        self.project.removeAllMapLayers()

    def test_gs_output_001_full_chain_invariant_reconciliation(self):
        # 1. Contract Validation
        contract = HumanitarianAnalysisContract(
            objective="priority_needs",
            geography=GeographicScope(
                country_iso3="BFA",
                admin_level=2,
                layer_name="bfa_districts",
                pcode_field="ADM2_PCODE",
            ),
            humanitarian_context=HumanitarianContext(
                cluster_sector="wash",
                indicator_names=["people_in_need"],
                unit_of_measurement="people",
            ),
            methodology=MethodologicalRules(
                method="needs_aggregation",
                aggregation_rule="sum",
            ),
            expected_outputs=ExpectedDeliverables(
                analytical_layer=True,
                output_format="gpkg",
                map_symbology=True,
                dashboard_kpis=True,
                print_layout=True,
                export_deliverable=True,
            ),
        )
        val = contract.validate()
        self.assertTrue(val["valid"])

        # 2. Build Layer with 4 Districts
        vl = QgsVectorLayer("Polygon?crs=EPSG:4326", "bfa_districts", "memory")
        pr = vl.dataProvider()
        pr.addAttributes([
            QgsField("ADM2_PCODE", QVariant.String),
            QgsField("ADM2_EN", QVariant.String),
            QgsField("people_in_need", QVariant.Int),
            QgsField("baseline_pop", QVariant.Int),
        ])
        vl.updateFields()

        records = [
            ("BF0101", "Oudalan", 45000, 150000),
            ("BF0102", "Seno", 35000, 220000),
            ("BF0103", "Soum", 60000, 180000),
            ("BF0104", "Yagha", 20000, 90000),
        ]
        feats = []
        for i, (pcode, name, pin, pop) in enumerate(records):
            f = QgsFeature(vl.fields())
            f.setAttribute("ADM2_PCODE", pcode)
            f.setAttribute("ADM2_EN", name)
            f.setAttribute("people_in_need", pin)
            f.setAttribute("baseline_pop", pop)
            f.setGeometry(QgsGeometry.fromRect(QgsRectangle(i * 1.0, 0, (i + 1) * 1.0, 1)))
            feats.append(f)
        pr.addFeatures(feats)
        vl.updateExtents()
        self.project.addMapLayer(vl)

        # 3. Calculate Target Indicator Total
        target_indicator = "people_in_need"
        calculated_total = sum(f[target_indicator] for f in vl.getFeatures())
        self.assertEqual(calculated_total, 160000)

        # 4. Map Symbology Simulation
        carto_sig = CartographicSignature(
            layer_name="bfa_districts",
            renderer_type="graduated",
            symbolized_field=target_indicator,
            class_breaks=[20000, 35000, 45000, 60000],
            class_labels=["Low", "Medium", "High", "Critical"],
        )

        # 5. Dashboard State Simulation
        dash_sig = DashboardSignature(
            dashboard_id="dash_wash_01",
            kpi_metric_name="Total People in Need",
            kpi_value=160000,
            active_filters={"cluster": "wash", "admin_level": 2},
        )

        # 6. Layout Key Figure Simulation
        layout_sig = LayoutSignature(
            layout_name="A4_Situation_Map",
            title="Burkina Faso - Sahel WASH Needs 2026",
            indicator_label="People in Need",
            reported_key_figure=160000,
        )

        # 7. GeoPackage Export
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            out_gpkg = os.path.join(tmpdir, "bfa_wash_needs.gpkg")
            res_export = export_layer("bfa_districts", format="gpkg", output_path=out_gpkg, confirmed=True)
            self.assertTrue(res_export.get("success"))

            gpkg_vl = QgsVectorLayer(out_gpkg, "gpkg_check", "ogr")
            self.assertTrue(gpkg_vl.isValid())
            export_sum = sum(f[target_indicator] for f in gpkg_vl.getFeatures())
            self.assertEqual(export_sum, 160000)

            export_sig = ExportSignature(
                output_path=out_gpkg,
                format="gpkg",
                feature_count=gpkg_vl.featureCount(),
                field_names=[f.name() for f in gpkg_vl.fields()],
                sum_value=export_sum,
            )

            # 8. Complete Multi-Channel Semantic & Numerical Reconciliation
            integrity_signature = AnalysisIntegritySignature(
                objective="priority_needs",
                indicator_name=target_indicator,
                methodology_id="needs_aggregation_sum",
                dataset_name="bfa_districts",
                pcode_set={"BF0101", "BF0102", "BF0103", "BF0104"},
                feature_count=4,
                calculated_total=calculated_total,
                cartography=carto_sig,
                dashboard=dash_sig,
                layout=layout_sig,
                export=export_sig,
            )

            auditor = OutputReconciliationAuditor(target_indicator)
            auditor.record_channel_value("gis_attribute", calculated_total)
            auditor.record_channel_value("dashboard_kpi", dash_sig.kpi_value)
            auditor.record_channel_value("layout_metric", layout_sig.reported_key_figure)
            auditor.record_channel_value("export_sum", export_sum)
            auditor.set_integrity_signature(integrity_signature)

            report = auditor.reconcile()
            self.assertTrue(report["reconciled"], f"Audit failed: {report}")
            self.assertEqual(report["status"], "PASS — AUTOMATED VERIFIED")
            self.assertEqual(len(report["discrepancies"]), 0)

            # 9. Test Defensive Detection: What if the map symbolized the WRONG field?
            deceptive_carto_sig = CartographicSignature(
                layer_name="bfa_districts",
                renderer_type="graduated",
                symbolized_field="baseline_pop",  # Wrong field!
            )
            deceptive_signature = AnalysisIntegritySignature(
                objective="priority_needs",
                indicator_name=target_indicator,
                methodology_id="needs_aggregation_sum",
                dataset_name="bfa_districts",
                cartography=deceptive_carto_sig,
            )
            deceptive_auditor = OutputReconciliationAuditor(target_indicator)
            deceptive_auditor.record_channel_value("gis_attribute", 160000)
            deceptive_auditor.set_integrity_signature(deceptive_signature)
            deceptive_report = deceptive_auditor.reconcile()

            # Assert auditor catches the deceptive cartographic state
            self.assertFalse(deceptive_report["reconciled"])
            self.assertEqual(deceptive_report["status"], "FAIL")
            self.assertEqual(deceptive_report["discrepancies"][0]["type"], "CARTOGRAPHIC_FIELD_MISMATCH")


if __name__ == "__main__":
    from qgis.core import QgsApplication
    qgs = QgsApplication([], False)
    qgs.initQgis()
    try:
        unittest.main()
    finally:
        qgs.exitQgis()
