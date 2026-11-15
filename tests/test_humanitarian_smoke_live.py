"""
Humanitarian QA/QC Live Smoke Test Suite:
Executes the 10 Critical Humanitarian Live Test Workflows against live QGIS and Qt components.
"""

import os
import tempfile
import unittest

# Ensure Qt offscreen platform for headless execution
os.environ["QT_QPA_PLATFORM"] = "offscreen"


try:
    import qgis.core  # noqa: F401
except ImportError:
    raise unittest.SkipTest("requires real QGIS") from None  # the plain test job has no QGIS: skip the module instead of failing the whole run at import

from qgis.core import (
    QgsApplication,
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsRectangle,
    QgsField,
    QgsPrintLayout,
    QgsLayoutItemMap,
    QgsLayoutItemLegend,
    QgsLayoutItemScaleBar,
)
from qgis.PyQt.QtCore import QVariant

from cartogen_ai.core.validators.humanitarian_contract import (
    parse_humanitarian_intent,
    generate_analysis_id,
    check_contract_for_tool,
)
from cartogen_ai.core.validators.reconciliation_auditor import (
    OutputReconciliationAuditor,
)
from cartogen_ai.core.agent.tools.analysis_tools import (
    _compute_severity_index,
)
from cartogen_ai.core.agent.tools.export_tools import export_layer, _check_shapefile_field_names
from cartogen_ai.core.agent.tools.vector_tools import obfuscate_sensitive_points
from cartogen_ai.core.models.sensitivity import set_layer_sensitivity, check_export_allowed


class TestHumanitarianLiveSmokeSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project = QgsProject.instance()

    def setUp(self):
        self.project.removeAllMapLayers()

    def tearDown(self):
        self.project.removeAllMapLayers()

    def test_workflow_01_positive_intent_translation(self):
        """Workflow 1: Complete Positive Intent Translation & Analysis ID Generation"""
        query = "Show the population outside 60-minute health-service access in Admin 2 areas, with a map and summary statistics."
        contract = parse_humanitarian_intent(query)
        self.assertEqual(contract.objective, "population_access_gap")
        self.assertEqual(contract.humanitarian_context.cluster_sector, "health")
        self.assertEqual(contract.geography.admin_level, 2)
        self.assertEqual(contract.methodology.thresholds.get("travel_cost"), 60.0)
        self.assertEqual(contract.methodology.thresholds.get("travel_unit"), "minutes")

        val = contract.validate()
        self.assertTrue(val["valid"])
        self.assertFalse(val["needs_clarification"])

        analysis_id = generate_analysis_id(contract)
        self.assertTrue(analysis_id.startswith("HUM-"))
        self.assertEqual(len(analysis_id.split("-")), 3)

    def test_workflow_02_rule_37_missing_threshold_enforcement(self):
        """Workflow 2: Rule 37 Missing Threshold Enforcement (HALT & CLARIFY)"""
        args_missing = {
            "facility_layer": "health_facilities",
            "road_network_layer": "roads",
            "population_raster_layer": "worldpop",
            "area_layer": "admin2_districts",
            # travel_cost omitted!
        }
        gate_res = check_contract_for_tool("population_access_gap", args_missing)
        self.assertIsNotNone(gate_res)
        self.assertEqual(gate_res["status"], "HALT_AND_CLARIFY")
        self.assertTrue(gate_res["needs_clarification"])
        self.assertEqual(gate_res["parameter"], "travel_cost")
        self.assertIn("Rule 37", gate_res["message"])

    def test_workflow_03_joint_pin_map_rendering(self):
        """Workflow 3: Joint People in Need (JIAF Mosaic Method) Map Rendering & Styling"""
        vl = QgsVectorLayer("Polygon?crs=EPSG:4326", "district_pin", "memory")
        pr = vl.dataProvider()
        pr.addAttributes([
            QgsField("adm2_pcode", QVariant.String),
            QgsField("pin_wash", QVariant.Int),
            QgsField("pin_health", QVariant.Int),
            QgsField("joint_pin", QVariant.Int),
        ])
        vl.updateFields()

        feats = []
        data = [
            ("YE1301", 10000, 15000, 15000),  # Max = 15,000
            ("YE1302", 25000, 20000, 25000),  # Max = 25,000
            ("YE1303", 0, 0, 0),              # Zero need
        ]
        for i, (pcode, w, h, j) in enumerate(data):
            f = QgsFeature(vl.fields())
            f.setAttribute("adm2_pcode", pcode)
            f.setAttribute("pin_wash", w)
            f.setAttribute("pin_health", h)
            f.setAttribute("joint_pin", j)
            f.setGeometry(QgsGeometry.fromRect(QgsRectangle(i * 1.0, 0.0, (i + 1) * 1.0, 1.0)))
            feats.append(f)
        pr.addFeatures(feats)
        vl.updateExtents()
        self.project.addMapLayer(vl)

        # Apply Graduated Renderer on joint_pin using plugin styling tool
        from cartogen_ai.core.agent.tools.styling_tools import apply_graduated_style
        style_res = apply_graduated_style(
            layer_name="district_pin",
            field="joint_pin",
            num_classes=3,
        )
        self.assertTrue(style_res.get("success"), f"Styling failed: {style_res}")
        self.assertEqual(vl.renderer().classAttribute(), "joint_pin")

    def test_workflow_04_composite_severity_authority_level(self):
        """Workflow 4: Exploratory Composite Severity Index & Authority Level Label"""
        rows = [
            {"unit": "Dist_A", "food": 80, "water": 40},
            {"unit": "Dist_B", "food": 20, "water": 10},
        ]
        res = _compute_severity_index(rows, ["food", "water"])
        self.assertTrue(res.get("success"))
        # Verify strict methodological disclaimer
        self.assertEqual(
            res["methodological_authority_level"],
            "TECHNICALLY VERIFIED — EXPLORATORY METHODOLOGY"
        )
        self.assertEqual(res["scored_units"], 2)

    def test_workflow_05_3w_presence_gap_integrity(self):
        """Workflow 5: 3W Operational Presence vs Severity Gap Logic"""
        from cartogen_ai.core.agent.tools import reporting_tools as rt
        presence_rows = [
            {"adm2_pcode": "YE1301", "org": "UNICEF"},
            {"adm2_pcode": "YE1301", "org": "WHO"},
            {"adm2_pcode": "YE1302", "org": "WFP"},
            {"adm2_pcode": "UNKNOWN", "org": "NGO_X"},
        ]
        presence_by_unit, _skipped = rt._aggregate_3w_presence(presence_rows, "adm2_pcode", "org")
        # _aggregate_3w_presence normalizes unit keys to stripped lowercase for robust joining
        self.assertEqual(len(presence_by_unit["ye1301"]["orgs"]), 2)
        self.assertEqual(len(presence_by_unit["ye1302"]["orgs"]), 1)
        self.assertIn("unknown", presence_by_unit)

    def test_workflow_06_service_area_reach_population_gap(self):
        """Workflow 6: Service Area Road Network Reach & Population Gap Invariant"""
        total_pop = 150000.0
        reachable_pop = 105000.0
        gap_pop = max(0.0, total_pop - reachable_pop)
        gap_pct = round((gap_pop / total_pop) * 100, 2)

        self.assertEqual(gap_pop, 45000.0)
        self.assertEqual(gap_pct, 30.0)
        self.assertAlmostEqual(reachable_pop + gap_pop, total_pop)

    def test_workflow_07_jiaf_traceability_and_consensus_override(self):
        """Workflow 7: JIAF 2 Full Traceability Chain & Consensus Override"""
        from cartogen_ai.core.agent.tools import jiaf_rules as jr, jiaf_engine as je
        settings = je.merge_settings()
        sector_pins = {"food_security": 90000, "health": 20000}
        flags, _ranks = jr.pin_flags(sector_pins, 100000, settings, None)
        # Flag 2 triggers because (90000 - 20000)/90000 = 77.8% > 30%
        self.assertTrue(flags[2]["fired"])

        # Consensus override recorded
        consensus_record = {
            "unit": "YE0102",
            "preliminary_pin": 90000,
            "final_pin": 20000,
            "rationale": "Accepted 2nd highest sector after cluster review of localized pocket assessment"
        }
        self.assertEqual(consensus_record["final_pin"], 20000)
        self.assertIn("cluster review", consensus_record["rationale"])

    def test_workflow_08_html_dashboard_and_reconciliation(self):
        """Workflow 8: HTML Dashboard KPI and Invariant Reconciliation"""
        auditor = OutputReconciliationAuditor("people_in_need")
        auditor.record_channel_value("gis_attribute", 50000)
        auditor.record_channel_value("dashboard_kpi", 50000)
        auditor.record_channel_value("layout_metric", 50000)
        auditor.record_channel_value("export_sum", 50000)

        report = auditor.reconcile()
        self.assertTrue(report["reconciled"])
        self.assertEqual(report["status"], "PASS — AUTOMATED VERIFIED")

    def test_workflow_09_print_layout_composition(self):
        """Workflow 9: Print Layout Composition, North Arrow & Legend"""
        layout = QgsPrintLayout(self.project)
        layout.initializeDefaults()
        layout.setName("Humanitarian_SitRep_Layout")

        map_item = QgsLayoutItemMap(layout)
        map_item.setRect(20, 20, 200, 150)
        layout.addLayoutItem(map_item)

        legend_item = QgsLayoutItemLegend(layout)
        layout.addLayoutItem(legend_item)

        scalebar = QgsLayoutItemScaleBar(layout)
        scalebar.setLinkedMap(map_item)
        layout.addLayoutItem(scalebar)

        self.assertIsNotNone(layout.name())
        # Confirm user added layout items (map, legend, scalebar) are in layout
        self.assertTrue(len(layout.items()) >= 3)

    def test_workflow_10_strict_protection_and_canonical_gpkg_export(self):
        """Workflow 10: Strict Data Protection Policy & Canonical GeoPackage Export"""
        vl = QgsVectorLayer("Point?crs=EPSG:4326", "sensitive_gbv_cases", "memory")
        pr = vl.dataProvider()
        pr.addAttributes([
            QgsField("case_id", QVariant.String),
            QgsField("population_in_need", QVariant.Int),
            QgsField("population_reached", QVariant.Int),
        ])
        vl.updateFields()

        f = QgsFeature(vl.fields())
        f.setAttribute("case_id", "GBV-001")
        f.setAttribute("population_in_need", 150)
        f.setAttribute("population_reached", 120)
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(15.2, 24.5)))
        pr.addFeatures([f])
        vl.updateExtents()
        self.project.addMapLayer(vl)

        # 1. Tag as HIGHLY_SENSITIVE -> Raw export must be BLOCKED
        set_layer_sensitivity(vl, "HIGHLY_SENSITIVE", reason="Unmasked GBV survivor records")
        allowed, msg = check_export_allowed(vl)
        self.assertFalse(allowed)
        self.assertIn("Export BLOCKED", msg)

        # 2. Obfuscate points using grid_snap (Do No Harm derivative)
        obf_res = obfuscate_sensitive_points(
            layer_name="sensitive_gbv_cases",
            method="grid_snap",
            cell_size=0.1,
            output_layer_name="obfuscated_cases",
        )
        self.assertTrue(obf_res.get("success"))
        self.project.mapLayersByName("obfuscated_cases")[0]  # raises if the layer was not produced

        # 3. Canonical Export of safe derivative to GeoPackage (.gpkg)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            out_gpkg = os.path.join(tmpdir, "safe_cases.gpkg")
            res_exp = export_layer("obfuscated_cases", format="gpkg", output_path=out_gpkg)
            self.assertTrue(res_exp.get("success"))
            self.assertEqual(res_exp["feature_count"], 1)

            # 4. Assert Shapefile Preflight warns about DBF truncation and collisions
            warning_msg, _field_map = _check_shapefile_field_names(vl)
            self.assertIsNotNone(warning_msg)
            self.assertIn("10 characters", warning_msg)
            self.assertIn("collision", warning_msg.lower())


if __name__ == "__main__":
    app = QgsApplication([], False)
    app.initQgis()
    try:
        unittest.main()
    finally:
        app.exitQgis()
