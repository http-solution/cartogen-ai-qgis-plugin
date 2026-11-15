"""
Full Humanitarian Live Smoke Test Suite:
Exhaustively tests all humanitarian tools across 8 Scenario Families with realistic sample data,
records all inputs and outputs in a structured JSON report, and renders high-resolution PNG
screenshots from live QGIS 4.2.3.
"""

import os
import sys
import json
import shutil
import tempfile
import unittest
import datetime

# Ensure Qt offscreen platform
os.environ["QT_QPA_PLATFORM"] = "offscreen"


try:
    import qgis.core  # noqa: F401
except ImportError:
    raise unittest.SkipTest("requires real QGIS") from None  # the plain test job has no QGIS: skip the module instead of failing the whole run at import

from qgis.core import (
    QgsApplication,
    QgsProject,
    QgsVectorLayer,
    QgsRasterLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsRectangle,
    QgsField,
    QgsCoordinateReferenceSystem,
    QgsMapSettings,
    QgsMapRendererSequentialJob,
    QgsLayoutExporter,
)
from qgis.PyQt.QtCore import QVariant, QSize
from qgis.PyQt.QtGui import QColor

# Initialize QgsApplication if running headless
if not QgsApplication.instance():
    _qgs_app = QgsApplication([], False)
    _qgs_app.initQgis()

from processing.core.Processing import Processing
Processing.initialize()
from qgis.analysis import QgsNativeAlgorithms
_reg = QgsApplication.processingRegistry()
if not _reg.providerById("native"):
    _reg.addProvider(QgsNativeAlgorithms())

# Humanitarian Tools Imports
from cartogen_ai.core.agent.tools.analysis_tools import (
    calculate_severity_index,
    calculate_population_in_need,
    calculate_presence_gap,
    analyze_incident_trend,
    forecast_trend,
)
from cartogen_ai.core.agent.tools.allocation_tools import calculate_allocation_envelope
from cartogen_ai.core.agent.tools.reporting_tools import (
    load_3w_data,
    generate_sector_coverage_report,
    aggregate_data,
)
from cartogen_ai.core.agent.tools.pcode_validation_tools import (
    check_pcode_hierarchy,
    check_pcode_uniqueness,
)
from cartogen_ai.core.agent.tools.logistics_tools import (
    calculate_service_area,
    population_access_gap,
    travel_time_matrix,
    optimal_hub_siting,
    location_allocation,
    estimate_road_speeds,
)
from cartogen_ai.core.agent.tools.jiaf_inputs import record_jiaf_setup, get_jiaf_setup
from cartogen_ai.core.agent.tools.jiaf_engine import compute_jiaf_preliminary
from cartogen_ai.core.agent.tools.jiaf_patterns import compute_jiaf_patterns
from cartogen_ai.core.agent.tools.jiaf_review import record_jiaf_decisions, finalize_jiaf_results
from cartogen_ai.core.agent.tools.hazard_monitoring_tools import (
    fetch_gdacs_disaster_alerts,
    fetch_nasa_active_fires,
)
from cartogen_ai.core.agent.tools.trigger_tools import evaluate_forecast_trigger
from cartogen_ai.core.agent.tools.sensitivity_tools import set_layer_sensitivity, get_layer_sensitivity
from cartogen_ai.core.agent.tools.vector_tools import obfuscate_sensitive_points
from cartogen_ai.core.agent.tools.export_tools import (
    export_layer,
    generate_html_dashboard,
    generate_spatial_report,
)
from cartogen_ai.core.agent.tools.sampling_tools import design_sampling_frame
from cartogen_ai.core.agent.tools.survey_tools import aggregate_survey_indicator
from cartogen_ai.core.agent.tools.task_grid_tools import generate_mapping_task_grid
from cartogen_ai.core.agent.tools.qa_checklist_tools import generate_map_product_qa_checklist
from cartogen_ai.core.agent.tools.mcda_tools import calculate_mcda_ranking
from cartogen_ai.core.agent.tools.humanitarian_look_tools import apply_humanitarian_look
from cartogen_ai.core.agent.tools.styling_tools import apply_graduated_style, apply_categorized_style
from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
from cartogen_ai.core.agent.tools.raster_numpy import write_single_band
import numpy as np


# Was a hard-coded Windows folder (C:\http-solution\...), which on the Linux CI image made the renders and the final report land in oddly named
# folders and the report write fail in tearDownClass. CARTOGEN_SMOKE_OUTPUT overrides it for a run whose files should be kept.
OUTPUT_DIR = os.environ.get("CARTOGEN_SMOKE_OUTPUT") or tempfile.mkdtemp(prefix="hum_smoke_out_")
RENDERS_DIR = os.path.join(OUTPUT_DIR, "humanitarian_smoke_renders")
IO_REPORT_FILE = os.path.join(OUTPUT_DIR, "humanitarian_smoke_io_report.json")
os.makedirs(RENDERS_DIR, exist_ok=True)

# Global execution log tracking all I/O
SMOKE_EXECUTION_LOG = {
    "metadata": {
        "timestamp": datetime.datetime.now().isoformat(),
        "qgis_version": "4.2.3",
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "suite_name": "Full Humanitarian Live Smoke Test Suite",
        "total_families": 8,
    },
    "scenarios": []
}


def _render_layer_to_png(layers, output_png, extent=None, size=(1000, 700), bg_color=None):
    """Helper to render map layers to a PNG screenshot."""
    bg_color = bg_color or QColor(248, 249, 250)
    settings = QgsMapSettings()
    settings.setLayers(layers)
    if extent:
        settings.setExtent(extent)
    elif layers:
        combined_box = QgsRectangle()
        combined_box.setNull()
        for lyr in layers:
            combined_box.combineExtentWith(lyr.extent())
        settings.setExtent(combined_box)
    settings.setOutputSize(QSize(*size))
    settings.setBackgroundColor(bg_color)
    job = QgsMapRendererSequentialJob(settings)
    job.start()
    job.waitForFinished()
    img = job.renderedImage()
    img.save(output_png)
    job.deleteLater()           # a render job left alive until interpreter exit is one more Qt object for the CI job's shutdown crash to trip on
    return os.path.exists(output_png) and os.path.getsize(output_png) > 0


class TestHumanitarianFullSmokeLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project = QgsProject.instance()
        cls.temp_dir = tempfile.mkdtemp(prefix="hum_smoke_")

    @classmethod
    def tearDownClass(cls):
        cls.project.removeAllMapLayers()
        shutil.rmtree(cls.temp_dir, ignore_errors=True)
        # Write final JSON I/O report
        with open(IO_REPORT_FILE, "w", encoding="utf-8") as f:
            json.dump(SMOKE_EXECUTION_LOG, f, indent=2, default=str)
        print(f"\n[REPORT] Saved full humanitarian I/O report to: {IO_REPORT_FILE}")

    def setUp(self):
        self.project.removeAllMapLayers()

    # --- Scenario Family 1: Needs, PiN & Aid Allocation ---
    def test_scenario_01_needs_pin_and_allocation(self):
        """Scenario 1: Composite Severity Index, Population in Need, Exposure & Budget Allocation"""
        # 1. Create sample district polygons (Yemen UTM 38N: EPSG:32638)
        adm_layer = QgsVectorLayer("Polygon?crs=EPSG:32638", "yemen_adm2", "memory")
        pr = adm_layer.dataProvider()
        pr.addAttributes([
            QgsField("adm2_pcode", QVariant.String),
            QgsField("adm2_name", QVariant.String),
            QgsField("population_total", QVariant.Double),
            QgsField("fcs_poor", QVariant.Double),
            QgsField("shelter_damage", QVariant.Double),
            QgsField("morbidity_rate", QVariant.Double),
            QgsField("water_access_pct", QVariant.Double),
        ])
        adm_layer.updateFields()

        # 4 districts: Sanhan, Bani Hushaysh, Crater, Al Mualla
        features_data = [
            ("YE1301", "Sanhan", 150000.0, 35.0, 45.0, 22.0, 40.0, "POLYGON((400000 1600000, 430000 1600000, 430000 1630000, 400000 1630000, 400000 1600000))"),
            ("YE1302", "Bani Hushaysh", 95000.0, 50.0, 60.0, 30.0, 25.0, "POLYGON((430000 1600000, 460000 1600000, 460000 1630000, 430000 1630000, 430000 1600000))"),
            ("YE1401", "Crater", 110000.0, 20.0, 15.0, 12.0, 75.0, "POLYGON((400000 1570000, 430000 1570000, 430000 1600000, 400000 1600000, 400000 1570000))"),
            ("YE1402", "Al Mualla", 80000.0, 28.0, 35.0, 18.0, 60.0, "POLYGON((430000 1570000, 460000 1570000, 460000 1600000, 430000 1600000, 430000 1570000))"),
        ]
        feats = []
        for pcode, name, pop, fcs, shelter, morb, wash, wkt in features_data:
            f = QgsFeature(adm_layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(wkt))
            f.setAttributes([pcode, name, pop, fcs, shelter, morb, wash])
            feats.append(f)
        pr.addFeatures(feats)
        adm_layer.updateExtents()
        self.project.addMapLayer(adm_layer)

        # 2. Synthetic gridded population raster
        ext = adm_layer.extent()
        data = np.full((10, 10), 1000.0, dtype='float32')
        meta = {
            'geotransform': (ext.xMinimum(), (ext.xMaximum() - ext.xMinimum()) / 10.0, 0,
                             ext.yMaximum(), 0, -(ext.yMaximum() - ext.yMinimum()) / 10.0),
            'projection': QgsCoordinateReferenceSystem('EPSG:32638').toWkt()
        }
        pop_raster_path = write_single_band(data, meta, nodata=-9999)
        pop_raster = QgsRasterLayer(pop_raster_path, "yemen_population_count")
        self.project.addMapLayer(pop_raster)

        # 3. Incident point layer for trend analysis
        inc_layer = QgsVectorLayer("Point?crs=EPSG:32638", "conflict_incidents", "memory")
        inc_pr = inc_layer.dataProvider()
        inc_pr.addAttributes([
            QgsField("incident_id", QVariant.String),
            QgsField("event_date", QVariant.String),
            QgsField("fatalities", QVariant.Int),
        ])
        inc_layer.updateFields()
        inc_feats = []
        for i, (x, y, dt, fat) in enumerate([
            (410000, 1610000, "2026-01-10", 3),
            (420000, 1620000, "2026-01-15", 5),
            (440000, 1615000, "2026-02-05", 2),
            (445000, 1625000, "2026-02-20", 8),
            (415000, 1585000, "2026-03-01", 1),
            (450000, 1590000, "2026-03-12", 4),
        ]):
            f = QgsFeature(inc_layer.fields())
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
            f.setAttributes([f"INC-{i+1}", dt, fat])
            inc_feats.append(f)
        inc_pr.addFeatures(inc_feats)
        inc_layer.updateExtents()
        self.project.addMapLayer(inc_layer)

        # TOOL EXECUTION 1: calculate_severity_index
        sev_in = {
            "layer_name": adm_layer.name(),
            "indicator_fields": ["fcs_poor", "shelter_damage", "morbidity_rate", "water_access_pct"],
            "unit_name_field": "adm2_name",
            "weights": {"fcs_poor": 0.35, "shelter_damage": 0.25, "morbidity_rate": 0.25, "water_access_pct": 0.15},
            "invert_indicators": ["water_access_pct"],
            "output_field": "severity_score",
            "confirmed": True
        }
        sev_out = calculate_severity_index(**sev_in)
        self.assertTrue(sev_out.get("success"), sev_out)
        self.assertEqual(sev_out["methodological_authority_level"], "TECHNICALLY VERIFIED — EXPLORATORY METHODOLOGY")

        # TOOL EXECUTION 2: calculate_population_in_need
        pin_in = {
            "layer_name": adm_layer.name(),
            "indicator_fields": ["fcs_poor", "shelter_damage", "morbidity_rate"],
            "unit_name_field": "adm2_name",
            "population_raster_layer": pop_raster.name(),
            "output_field": "calc_pin",
            "confirmed": True
        }
        pin_out = calculate_population_in_need(**pin_in)
        self.assertTrue(pin_out.get("success"), pin_out)
        self.assertIn("population_in_need", pin_out)
        self.assertGreater(pin_out["population_in_need"], 0)

        # TOOL EXECUTION 3: analyze_incident_trend & forecast_trend
        trend_in = {
            "point_layer": inc_layer.name(),
            "date_field": "event_date",
            "zone_layer": adm_layer.name(),
            "zone_name_field": "adm2_name",
            "period_days": 30,
            "periods_ahead": 1
        }
        trend_out = analyze_incident_trend(**trend_in)
        self.assertTrue(trend_out.get("success"), trend_out)

        fc_in = {
            "layer_name": inc_layer.name(),
            "date_field": "event_date",
            "value_field": "fatalities",
            "periods_ahead": 3
        }
        fc_out = forecast_trend(**fc_in)
        self.assertTrue(fc_out.get("success"), fc_out)

        # TOOL EXECUTION 4: calculate_allocation_envelope
        alloc_in = {
            "layer_name": adm_layer.name(),
            "budget": 10000000.0,
            "need_field": "severity_score",
            "population_field": "population_total",
            "unit_name_field": "adm2_name",
            "output_field": "allocated_aid_usd",
            "confirmed": True
        }
        alloc_out = calculate_allocation_envelope(**alloc_in)
        self.assertTrue(alloc_out.get("success"), alloc_out)
        self.assertAlmostEqual(alloc_out["allocated"], 10000000.0, delta=10.0)

        # Style & Render Screenshot 1
        apply_graduated_style(adm_layer.name(), "severity_score", mode="auto", cluster="food_security")
        screenshot_path = os.path.join(RENDERS_DIR, "screenshot_01_pin_severity_map.png")
        rendered = _render_layer_to_png([adm_layer, inc_layer], screenshot_path)
        self.assertTrue(rendered)

        # Log scenario
        SMOKE_EXECUTION_LOG["scenarios"].append({
            "scenario_id": "SCENARIO-HUM-01",
            "name": "Humanitarian Needs, Composite Severity & Aid Allocation",
            "tools_covered": ["calculate_severity_index", "calculate_population_in_need", "analyze_incident_trend", "forecast_trend", "calculate_allocation_envelope", "apply_graduated_style"],
            "inputs": {"severity": sev_in, "pin": pin_in, "trend": trend_in, "forecast": fc_in, "allocation": alloc_in},
            "outputs": {"severity": sev_out, "pin": pin_out, "trend": trend_out, "forecast": fc_out, "allocation": alloc_out},
            "screenshot": "screenshot_01_pin_severity_map.png"
        })

    # --- Scenario Family 2: Operational Coordination & 3W Presence ---
    def test_scenario_02_3w_presence_and_coordination(self):
        """Scenario 2: 3W Operational Presence vs Severity Gap, P-Code Validation & Sector Coverage"""
        # Create base admin districts
        adm_layer = QgsVectorLayer("Polygon?crs=EPSG:32638", "adm_3w_base", "memory")
        pr = adm_layer.dataProvider()
        pr.addAttributes([
            QgsField("adm2_pcode", QVariant.String),
            QgsField("adm2_name", QVariant.String),
            QgsField("adm1_pcode", QVariant.String),
            QgsField("need_severity", QVariant.Double),
        ])
        adm_layer.updateFields()
        f1 = QgsFeature(adm_layer.fields())
        f1.setGeometry(QgsGeometry.fromWkt("POLYGON((400000 1600000, 430000 1600000, 430000 1630000, 400000 1630000, 400000 1600000))"))
        f1.setAttributes(["YE1301", "Sanhan", "YE13", 4.2])
        f2 = QgsFeature(adm_layer.fields())
        f2.setGeometry(QgsGeometry.fromWkt("POLYGON((430000 1600000, 460000 1600000, 460000 1630000, 430000 1630000, 430000 1600000))"))
        f2.setAttributes(["YE1302", "Bani Hushaysh", "YE13", 4.8])
        f3 = QgsFeature(adm_layer.fields())
        f3.setGeometry(QgsGeometry.fromWkt("POLYGON((400000 1570000, 430000 1570000, 430000 1600000, 400000 1600000, 400000 1570000))"))
        f3.setAttributes(["YE1401", "Crater", "YE14", 2.1])
        pr.addFeatures([f1, f2, f3])
        adm_layer.updateExtents()
        self.project.addMapLayer(adm_layer)

        # Write sample 3W CSV file
        csv_3w_path = os.path.join(self.temp_dir, "yemen_3w_operational.csv")
        with open(csv_3w_path, "w", encoding="utf-8") as f:
            f.write("org,cluster,adm2_pcode,status,reached_beneficiaries,target_beneficiaries\n")
            f.write("UNICEF,WASH,YE1301,active,45000,50000\n")
            f.write("WHO,Health,YE1301,active,30000,40000\n")
            f.write("WFP,Food Security,YE1302,active,80000,100000\n")
            f.write("MSF,Health,YE1401,active,25000,30000\n")
            f.write("ICRC,Protection,YE1301,active,12000,15000\n")

        # TOOL EXECUTION 1: load_3w_data
        load_3w_in = {
            "file_path": csv_3w_path,
            "admin_field": "adm2_pcode",
            "org_field": "org",
            "sector_field": "cluster"
        }
        load_3w_out = load_3w_data(**load_3w_in)
        self.assertTrue(load_3w_out.get("success"), load_3w_out)
        self.assertEqual(load_3w_out["total_rows"], 5)

        # TOOL EXECUTION 2: calculate_presence_gap
        gap_in = {
            "layer_name": adm_layer.name(),
            "indicator_fields": ["need_severity"],
            "unit_name_field": "adm2_pcode",
            "presence_file_path": csv_3w_path,
            "presence_admin_field": "adm2_pcode",
            "presence_org_field": "org",
            "confirmed": True
        }
        gap_out = calculate_presence_gap(**gap_in)
        self.assertTrue(gap_out.get("success"), gap_out)

        # TOOL EXECUTION 3: generate_sector_coverage_report & aggregate_data
        rows = [
            {"cluster": "WASH", "reached": 45000, "target": 50000},
            {"cluster": "Health", "reached": 55000, "target": 70000},
            {"cluster": "Food Security", "reached": 80000, "target": 100000},
            {"cluster": "Protection", "reached": 12000, "target": 15000},
        ]
        rep_in = {"rows": rows, "group_by_field": "cluster", "reached_field": "reached", "target_field": "target"}
        rep_out = generate_sector_coverage_report(**rep_in)
        self.assertTrue(rep_out.get("success"), rep_out)

        agg_in = {"rows": rows, "group_by_field": "cluster", "value_field": "reached", "agg": "sum"}
        agg_out = aggregate_data(**agg_in)
        self.assertTrue(agg_out.get("success"), agg_out)

        # TOOL EXECUTION 4: check_pcode_uniqueness & check_pcode_hierarchy
        pcode_u_in = {"layer_name": adm_layer.name(), "pcode_field": "adm2_pcode"}
        pcode_u_out = check_pcode_uniqueness(**pcode_u_in)
        self.assertTrue(pcode_u_out.get("success"), pcode_u_out)

        pcode_h_in = {"layer_name": adm_layer.name(), "child_pcode_field": "adm2_pcode", "parent_pcode_field": "adm1_pcode"}
        pcode_h_out = check_pcode_hierarchy(**pcode_h_in)
        self.assertTrue(pcode_h_out.get("success"), pcode_h_out)

        # Screenshot 2
        apply_categorized_style(adm_layer.name(), "adm1_pcode")
        screenshot_path = os.path.join(RENDERS_DIR, "screenshot_02_3w_presence_gap_map.png")
        rendered = _render_layer_to_png([adm_layer], screenshot_path)
        self.assertTrue(rendered)

        SMOKE_EXECUTION_LOG["scenarios"].append({
            "scenario_id": "SCENARIO-HUM-02",
            "name": "3W Operational Coordination, Presence Gap & P-Code Validation",
            "tools_covered": ["load_3w_data", "calculate_presence_gap", "generate_sector_coverage_report", "aggregate_data", "check_pcode_uniqueness", "check_pcode_hierarchy", "apply_categorized_style"],
            "inputs": {"load_3w": load_3w_in, "gap": gap_in, "coverage_report": rep_in, "aggregate": agg_in, "pcode_unique": pcode_u_in, "pcode_hierarchy": pcode_h_in},
            "outputs": {"load_3w": load_3w_out, "gap": gap_out, "coverage_report": rep_out, "aggregate": agg_out, "pcode_unique": pcode_u_out, "pcode_hierarchy": pcode_h_out},
            "screenshot": "screenshot_02_3w_presence_gap_map.png"
        })

    # --- Scenario Family 3: Health & Logistics Accessibility ---
    def test_scenario_03_logistics_and_access_gaps(self):
        """Scenario 3: Road Service Area Catchments, Population Access Gap, Routing & Critical Links"""
        # 1. District boundary
        aoi_layer = QgsVectorLayer("Polygon?crs=EPSG:32638", "health_aoi", "memory")
        aoi_pr = aoi_layer.dataProvider()
        aoi_pr.addAttributes([QgsField("name", QVariant.String)])
        aoi_layer.updateFields()
        f_aoi = QgsFeature(aoi_layer.fields())
        f_aoi.setGeometry(QgsGeometry.fromWkt("POLYGON((400000 1600000, 440000 1600000, 440000 1640000, 400000 1640000, 400000 1600000))"))
        f_aoi.setAttributes(["Marib Central"])
        aoi_pr.addFeatures([f_aoi])
        aoi_layer.updateExtents()
        self.project.addMapLayer(aoi_layer)

        # 2. Road network lines
        roads_layer = QgsVectorLayer("LineString?crs=EPSG:32638", "road_network", "memory")
        roads_pr = roads_layer.dataProvider()
        roads_pr.addAttributes([
            QgsField("road_id", QVariant.String),
            QgsField("highway", QVariant.String),
            QgsField("speed_kph", QVariant.Double),
            QgsField("oneway", QVariant.String),
        ])
        roads_layer.updateFields()
        road_segments = [
            ("R1", "primary", 60.0, "no", "LINESTRING(405000 1610000, 420000 1620000)"),
            ("R2", "secondary", 40.0, "no", "LINESTRING(420000 1620000, 435000 1630000)"),
            ("R3", "primary", 60.0, "no", "LINESTRING(420000 1620000, 420000 1635000)"),
            ("R4", "tertiary", 30.0, "no", "LINESTRING(405000 1610000, 405000 1630000)"),
            ("R5", "secondary", 40.0, "no", "LINESTRING(405000 1630000, 420000 1635000)"),
        ]
        r_feats = []
        for rid, hw, spd, ow, wkt in road_segments:
            f = QgsFeature(roads_layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(wkt))
            f.setAttributes([rid, hw, spd, ow])
            r_feats.append(f)
        roads_pr.addFeatures(r_feats)
        roads_layer.updateExtents()
        self.project.addMapLayer(roads_layer)

        # 3. Health facility points
        hosp_layer = QgsVectorLayer("Point?crs=EPSG:32638", "health_facilities", "memory")
        hosp_pr = hosp_layer.dataProvider()
        hosp_pr.addAttributes([
            QgsField("facility_id", QVariant.String),
            QgsField("name", QVariant.String),
            QgsField("type", QVariant.String),
            QgsField("beds", QVariant.Int),
        ])
        hosp_layer.updateFields()
        h_feats = []
        for hid, hname, htype, beds, (x, y) in [
            ("HF-1", "Al-Thawra General Hospital", "Hospital", 120, (420000, 1620000)),
            ("HF-2", "Bani Hushaysh Health Center", "Clinic", 20, (435000, 1630000)),
        ]:
            f = QgsFeature(hosp_layer.fields())
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
            f.setAttributes([hid, hname, htype, beds])
            h_feats.append(f)
        hosp_pr.addFeatures(h_feats)
        hosp_layer.updateExtents()
        self.project.addMapLayer(hosp_layer)

        # 4. Population raster
        ext = aoi_layer.extent()
        data = np.full((10, 10), 2500.0, dtype='float32')
        meta = {
            'geotransform': (ext.xMinimum(), (ext.xMaximum() - ext.xMinimum()) / 10.0, 0,
                             ext.yMaximum(), 0, -(ext.yMaximum() - ext.yMinimum()) / 10.0),
            'projection': QgsCoordinateReferenceSystem('EPSG:32638').toWkt()
        }
        pop_p = write_single_band(data, meta, nodata=-9999)
        pop_r = QgsRasterLayer(pop_p, "health_pop_raster")
        self.project.addMapLayer(pop_r)

        # TOOL EXECUTION 1: estimate_road_speeds
        spd_in = {"road_network_layer": roads_layer.name(), "default_speed_kmh": 40, "confirmed": True}
        spd_out = estimate_road_speeds(**spd_in)
        self.assertTrue(spd_out.get("success"), spd_out)

        # TOOL EXECUTION 2: calculate_service_area (15000 meters / ~15km reach)
        sa_in = {
            "facility_layer": hosp_layer.name(),
            "road_network_layer": roads_layer.name(),
            "travel_cost": 15000,
            "strategy": "shortest",
            "default_speed": 50,
            "style_by_cost": True
        }
        sa_out = calculate_service_area(**sa_in)
        self.assertTrue(sa_out.get("success"), sa_out)

        # TOOL EXECUTION 3: population_access_gap
        gap_in = {
            "facility_layer": hosp_layer.name(),
            "road_network_layer": roads_layer.name(),
            "population_raster_layer": pop_r.name(),
            "area_layer": aoi_layer.name(),
            "travel_cost": 15000,
            "strategy": "shortest"
        }
        gap_out = population_access_gap(**gap_in)
        self.assertTrue(gap_out.get("success"), gap_out)
        self.assertIn("gap_population", gap_out)
        self.assertIn("reachable_population", gap_out)

        # TOOL EXECUTION 4: travel_time_matrix
        mat_in = {
            "origins_layer": hosp_layer.name(),
            "destinations_layer": hosp_layer.name(),
            "road_network_layer": roads_layer.name(),
            "strategy": "shortest"
        }
        mat_out = travel_time_matrix(**mat_in)
        self.assertTrue(mat_out.get("success"), mat_out)

        # TOOL EXECUTION 5: optimal_hub_siting & location_allocation
        hub_in = {"candidate_layer": hosp_layer.name(), "demand_layer": hosp_layer.name()}
        hub_out = optimal_hub_siting(**hub_in)
        self.assertTrue(hub_out.get("success"), hub_out)

        alloc_fac_in = {"candidate_layer": hosp_layer.name(), "demand_layer": hosp_layer.name(), "num_facilities": 1}
        alloc_fac_out = location_allocation(**alloc_fac_in)
        self.assertTrue(alloc_fac_out.get("success"), alloc_fac_out)

        # Screenshot 3
        screenshot_path = os.path.join(RENDERS_DIR, "screenshot_03_health_service_catchments.png")
        layers_to_render = [aoi_layer, roads_layer, hosp_layer]
        # Include service area layers if created
        for lyr in self.project.mapLayers().values():
            if "Service_Area" in lyr.name() or "Catchment" in lyr.name() or "Hulls" in lyr.name():
                layers_to_render.insert(1, lyr)
        rendered = _render_layer_to_png(layers_to_render, screenshot_path)
        self.assertTrue(rendered)

        SMOKE_EXECUTION_LOG["scenarios"].append({
            "scenario_id": "SCENARIO-HUM-03",
            "name": "Health Accessibility, Service Area Catchments & Population Access Gap",
            "tools_covered": ["estimate_road_speeds", "calculate_service_area", "population_access_gap", "travel_time_matrix", "optimal_hub_siting", "location_allocation"],
            "inputs": {"speeds": spd_in, "service_area": sa_in, "access_gap": gap_in, "matrix": mat_in, "hub": hub_in, "location_alloc": alloc_fac_in},
            "outputs": {"speeds": spd_out, "service_area": sa_out, "access_gap": gap_out, "matrix": mat_out, "hub": hub_out, "location_alloc": alloc_fac_out},
            "screenshot": "screenshot_03_health_service_catchments.png"
        })

    # --- Scenario Family 4: JIAF 2.0 Needs Assessment Framework ---
    def test_scenario_04_jiaf_needs_assessment(self):
        """Scenario 4: JIAF 2.0 Ingestion, Consensus Setup, Deterministic Preliminary Severity & Finalization"""
        # 1. Create sample JIAF input CSV with standard HXL tags
        jiaf_csv = os.path.join(self.temp_dir, "jiaf_2026_input_indicators.csv")
        with open(jiaf_csv, "w", encoding="utf-8") as f:
            f.write("Admin PCode,Admin Name,Population,FSAC Severity,FSAC PiN,WASH Severity,WASH PiN,Health Severity,Health PiN\n")
            f.write("#adm2 +code,#adm2 +name,#population,#severity +fsac,#inneed +fsac,#severity +wsh,#inneed +wsh,#severity +hea,#inneed +hea\n")
            f.write("YE1301,Sanhan,150000,4,65000,3,45000,3,38000\n")
            f.write("YE1302,Bani Hushaysh,95000,5,55000,4,48000,4,42000\n")
            f.write("YE1401,Crater,110000,2,18000,2,12000,2,15000\n")
            f.write("YE1402,Al Mualla,80000,3,25000,3,20000,2,16000\n")

        # 2. Polygon layer for JIAF visualization
        jiaf_poly = QgsVectorLayer("Polygon?crs=EPSG:32638", "jiaf_districts", "memory")
        pr = jiaf_poly.dataProvider()
        pr.addAttributes([
            QgsField("Admin_Pcode", QVariant.String),
            QgsField("Admin_Name", QVariant.String),
            QgsField("Population", QVariant.Double),
            QgsField("FS_Severity", QVariant.Int),
            QgsField("WASH_Severity", QVariant.Int),
            QgsField("Health_Severity", QVariant.Int),
        ])
        jiaf_poly.updateFields()
        f1 = QgsFeature(jiaf_poly.fields())
        f1.setGeometry(QgsGeometry.fromWkt("POLYGON((400000 1600000, 430000 1600000, 430000 1630000, 400000 1630000, 400000 1600000))"))
        f1.setAttributes(["YE1301", "Sanhan", 150000, 4, 3, 3])
        f2 = QgsFeature(jiaf_poly.fields())
        f2.setGeometry(QgsGeometry.fromWkt("POLYGON((430000 1600000, 460000 1600000, 460000 1630000, 430000 1630000, 430000 1600000))"))
        f2.setAttributes(["YE1302", "Bani Hushaysh", 95000, 5, 4, 4])
        f3 = QgsFeature(jiaf_poly.fields())
        f3.setGeometry(QgsGeometry.fromWkt("POLYGON((400000 1570000, 430000 1570000, 430000 1600000, 400000 1600000, 400000 1570000))"))
        f3.setAttributes(["YE1401", "Crater", 110000, 2, 2, 2])
        pr.addFeatures([f1, f2, f3])
        jiaf_poly.updateExtents()
        self.project.addMapLayer(jiaf_poly)

        # TOOL EXECUTION 1: record_jiaf_setup & get_jiaf_setup
        setup_in = {
            "country": "YEM",
            "planning_cycle": "HNO 2026",
            "unit_of_analysis": "Admin 2",
            "manual_edition": "JIAF 2.0 Standard Guidance",
            "scope_note": "Multi-sector assessment for Marib and Aden governorates"
        }
        setup_out = record_jiaf_setup(**setup_in)
        self.assertTrue(setup_out.get("success"), setup_out)

        read_setup = get_jiaf_setup()
        self.assertTrue(read_setup.get("success"), read_setup)

        # TOOL EXECUTION 2: compute_jiaf_preliminary
        prelim_in = {
            "file_path": jiaf_csv,
            "confirmed": True
        }
        prelim_out = compute_jiaf_preliminary(**prelim_in)
        self.assertTrue(prelim_out.get("success"), prelim_out)
        self.assertIn("national_preliminary_pin", prelim_out)
        self.assertGreater(prelim_out["units"], 0)

        # TOOL EXECUTION 3: compute_jiaf_patterns
        pat_in = {"file_path": jiaf_csv, "confirmed": True}
        pat_out = compute_jiaf_patterns(**pat_in)
        self.assertTrue(pat_out.get("success"), pat_out)

        # TOOL EXECUTION 4: record_jiaf_decisions & finalize_jiaf_results
        dec_in = {
            "severity_decisions": [
                {
                    "unit": "YE1301",
                    "phase": 4,
                    "evidence_basis": "expert_judgement",
                    "evidence": "Expert consensus confirmed catastrophic food access constraint"
                }
            ]
        }
        dec_out = record_jiaf_decisions(**dec_in)
        self.assertTrue(dec_out.get("success"), dec_out)

        fin_in = {
            "file_path": jiaf_csv,
            "bulk_accepted_flags": [1],
            "bulk_rationale": "Endorsed by Inter-Cluster Coordination Group (ICCG)",
            "bulk_decided_by": "Yemen ICCG Panel",
            "confirmed": True
        }
        fin_out = finalize_jiaf_results(**fin_in)
        self.assertTrue(fin_out.get("success"), fin_out)

        # Screenshot 4: Graduated styling on JIAF severity phase
        apply_graduated_style(jiaf_poly.name(), "FS_Severity", breaks=[3, 4])
        screenshot_path = os.path.join(RENDERS_DIR, "screenshot_04_jiaf_preliminary_severity.png")
        rendered = _render_layer_to_png([jiaf_poly], screenshot_path)
        self.assertTrue(rendered)

        SMOKE_EXECUTION_LOG["scenarios"].append({
            "scenario_id": "SCENARIO-HUM-04",
            "name": "JIAF 2.0 Humanitarian Needs Assessment & Consensus Decision Lifecycle",
            "tools_covered": ["record_jiaf_setup", "get_jiaf_setup", "compute_jiaf_preliminary", "compute_jiaf_patterns", "record_jiaf_decisions", "finalize_jiaf_results"],
            "inputs": {"setup": setup_in, "preliminary": prelim_in, "patterns": pat_in, "decisions": dec_in, "finalize": fin_in},
            "outputs": {"setup": setup_out, "read_setup": read_setup, "preliminary": prelim_out, "patterns": pat_out, "decisions": dec_out, "finalize": fin_out},
            "screenshot": "screenshot_04_jiaf_preliminary_severity.png"
        })

    # --- Scenario Family 5: Hazard Monitoring & Early Warning ---
    def test_scenario_05_hazard_monitoring_and_triggers(self):
        """Scenario 5: Natural Hazard Bounding-Boxes, Pacific Antimeridian Queries & Early Warning Triggers"""
        # Create hazard boundary layer
        haz_layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "flood_hazard_extent", "memory")
        pr = haz_layer.dataProvider()
        pr.addAttributes([
            QgsField("hazard_id", QVariant.String),
            QgsField("hazard_type", QVariant.String),
            QgsField("severity_level", QVariant.String),
            QgsField("river_level_m", QVariant.Double),
        ])
        haz_layer.updateFields()
        f = QgsFeature(haz_layer.fields())
        f.setGeometry(QgsGeometry.fromWkt("POLYGON((44.0 15.0, 45.0 15.0, 45.0 16.0, 44.0 16.0, 44.0 15.0))"))
        f.setAttributes(["HAZ-2026-01", "Riverine Flood", "High", 7.8])
        pr.addFeatures([f])
        haz_layer.updateExtents()
        self.project.addMapLayer(haz_layer)

        # TOOL EXECUTION 1: evaluate_forecast_trigger
        trig_in = {
            "layer_name": haz_layer.name(),
            "value_field": "river_level_m",
            "threshold": 6.5,
            "comparison": ">=",
            "unit_field": "hazard_type"
        }
        trig_out = evaluate_forecast_trigger(**trig_in)
        self.assertTrue(trig_out.get("success"), trig_out)
        self.assertGreater(trig_out.get("activated_count", 0), 0)
        self.assertTrue(trig_out["units"][0]["activated"])

        # TOOL EXECUTION 2: fetch_nasa_active_fires with antimeridian BBOX (175, -20, -175, -10)
        from unittest.mock import patch, MagicMock
        fire_in = {
            "bbox": [175.0, -20.0, -175.0, -10.0],
            "days": 1,
            "layer_name": "Pacific Antimeridian Thermal Alerts"
        }
        with patch("cartogen_ai.core.agent.tools.hazard_monitoring_tools.CredentialManager.get_credential", return_value="TEST_FIRMS_KEY"):
            csv_mock = (
                "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight\n"
                "-15.5,178.2,340.5,0.4,0.4,2026-10-01,0230,N,high,2.0NRT,295.1,18.3,N\n"
                "-16.2,-178.8,335.1,0.4,0.4,2026-10-01,0230,N,high,2.0NRT,291.0,15.2,N\n"
            )
            with patch("cartogen_ai.core.agent.tools.hazard_monitoring_tools.urlopen_with_retry") as mock_url:
                resp = MagicMock()
                resp.read.return_value = csv_mock.encode("utf-8")
                resp.__enter__.return_value = resp
                mock_url.return_value = resp
                fire_out = fetch_nasa_active_fires(**fire_in)

        self.assertTrue(fire_out.get("success"), fire_out)
        self.assertGreater(fire_out.get("detection_count", 0), 0)

        # TOOL EXECUTION 3: fetch_gdacs_disaster_alerts
        gdacs_in = {"bbox": [40.0, 12.0, 50.0, 18.0], "min_alert_level": "Orange"}
        gdacs_out = fetch_gdacs_disaster_alerts(**gdacs_in)
        self.assertTrue(gdacs_out.get("success"), gdacs_out)

        # Screenshot 5
        screenshot_path = os.path.join(RENDERS_DIR, "screenshot_05_hazard_buffer_envelope.png")
        rendered = _render_layer_to_png([haz_layer], screenshot_path)
        self.assertTrue(rendered)

        SMOKE_EXECUTION_LOG["scenarios"].append({
            "scenario_id": "SCENARIO-HUM-05",
            "name": "Disaster Alerts, Antimeridian Crossing Hazards & Early Warning Triggers",
            "tools_covered": ["evaluate_forecast_trigger", "fetch_nasa_active_fires", "fetch_gdacs_disaster_alerts"],
            "inputs": {"trigger": trig_in, "fire_antimeridian": fire_in, "gdacs": gdacs_in},
            "outputs": {"trigger": trig_out, "fire_antimeridian": fire_out, "gdacs": gdacs_out},
            "screenshot": "screenshot_05_hazard_buffer_envelope.png"
        })

    # --- Scenario Family 6: Protection & "Do No Harm" Safeguards ---
    def test_scenario_06_protection_safeguards_and_geomasking(self):
        """Scenario 6: Protection Point Geomasking, Sensitivity Gates & Export Blocking"""
        # 1. Create sensitive GBV/Child protection facilities
        gbv_layer = QgsVectorLayer("Point?crs=EPSG:32638", "gbv_safe_spaces", "memory")
        pr = gbv_layer.dataProvider()
        pr.addAttributes([
            QgsField("case_id", QVariant.String),
            QgsField("service_type", QVariant.String),
            QgsField("caseload", QVariant.Int),
        ])
        gbv_layer.updateFields()
        pts = [
            ("CASE-01", "GBV Psychosocial Support", 15, (412000, 1614000)),
            ("CASE-02", "Child Safe Space", 28, (412500, 1614500)),
            ("CASE-03", "Legal Aid Clinic", 11, (411800, 1613500)),
        ]
        feats = []
        for cid, stype, cl, (x, y) in pts:
            f = QgsFeature(gbv_layer.fields())
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
            f.setAttributes([cid, stype, cl])
            feats.append(f)
        pr.addFeatures(feats)
        gbv_layer.updateExtents()
        self.project.addMapLayer(gbv_layer)

        # TOOL EXECUTION 1: set_layer_sensitivity & get_layer_sensitivity
        sens_in = {"layer_name": gbv_layer.name(), "level": "HIGHLY_SENSITIVE", "confirmed": True}
        sens_out = set_layer_sensitivity(**sens_in)
        self.assertTrue(sens_out.get("success"), sens_out)

        read_sens = get_layer_sensitivity(gbv_layer.name())
        self.assertEqual(read_sens["level"], "HIGHLY_SENSITIVE")

        # TOOL EXECUTION 2: export_layer (Raw) - MUST BE BLOCKED
        raw_export_in = {"layer_name": gbv_layer.name(), "format": "gpkg", "confirmed": True}
        raw_export_out = export_layer(**raw_export_in)
        self.assertFalse(raw_export_out.get("success"))
        self.assertTrue(raw_export_out.get("blocked_by_protection_policy"))

        # TOOL EXECUTION 3: obfuscate_sensitive_points (Geomasking)
        mask_in = {
            "layer_name": gbv_layer.name(),
            "method": "jitter",
            "radius": 1500,
            "output_layer_name": "gbv_geomasked_points",
            "seed": 42
        }
        mask_out = obfuscate_sensitive_points(**mask_in)
        self.assertTrue(mask_out.get("success"), mask_out)

        masked_layer = self.project.mapLayersByName("gbv_geomasked_points")[0]

        # TOOL EXECUTION 4: export_layer on sanitized/obfuscated derivative - MUST PASS
        masked_export_in = {"layer_name": masked_layer.name(), "format": "gpkg", "confirmed": True}
        masked_export_out = export_layer(**masked_export_in)
        self.assertTrue(masked_export_out.get("success"), masked_export_out)
        self.assertTrue(masked_export_out["output_path"].endswith(".gpkg"))

        # Screenshot 6: Raw vs Masked points
        screenshot_path = os.path.join(RENDERS_DIR, "screenshot_06_protection_geomasking_comparison.png")
        rendered = _render_layer_to_png([gbv_layer, masked_layer], screenshot_path)
        self.assertTrue(rendered)

        SMOKE_EXECUTION_LOG["scenarios"].append({
            "scenario_id": "SCENARIO-HUM-06",
            "name": "Protection Safeguards, 'Do No Harm' Sensitivity & Geomasking",
            "tools_covered": ["set_layer_sensitivity", "get_layer_sensitivity", "obfuscate_sensitive_points", "export_layer"],
            "inputs": {"sensitivity": sens_in, "raw_export": raw_export_in, "geomasking": mask_in, "masked_export": masked_export_in},
            "outputs": {"sensitivity": sens_out, "raw_export": raw_export_out, "geomasking": mask_out, "masked_export": masked_export_out},
            "screenshot": "screenshot_06_protection_geomasking_comparison.png"
        })

    # --- Scenario Family 7: Surveys, Sampling & MCDA ---
    def test_scenario_07_surveys_sampling_and_mcda(self):
        """Scenario 7: Stratified Survey Sampling Frame, Cluster Aggregation, Task Grid & MCDA Prioritization"""
        # 1. Stratum layer
        strata_layer = QgsVectorLayer("Polygon?crs=EPSG:32638", "strata_zones", "memory")
        pr = strata_layer.dataProvider()
        pr.addAttributes([
            QgsField("stratum_id", QVariant.String),
            QgsField("stratum_name", QVariant.String),
            QgsField("population", QVariant.Double),
            QgsField("vulnerability_idx", QVariant.Double),
            QgsField("access_barrier_score", QVariant.Double),
        ])
        strata_layer.updateFields()
        f1 = QgsFeature(strata_layer.fields())
        f1.setGeometry(QgsGeometry.fromWkt("POLYGON((400000 1600000, 420000 1600000, 420000 1620000, 400000 1620000, 400000 1600000))"))
        f1.setAttributes(["S1", "Urban Host", 80000, 0.45, 0.20])
        f2 = QgsFeature(strata_layer.fields())
        f2.setGeometry(QgsGeometry.fromWkt("POLYGON((420000 1600000, 440000 1600000, 440000 1620000, 420000 1620000, 420000 1600000))"))
        f2.setAttributes(["S2", "IDP Settlement", 65000, 0.85, 0.70])
        pr.addFeatures([f1, f2])
        strata_layer.updateExtents()
        self.project.addMapLayer(strata_layer)

        # 2. Household survey data layer
        survey_layer = QgsVectorLayer("Point?crs=EPSG:32638", "hh_survey_responses", "memory")
        pr_s = survey_layer.dataProvider()
        pr_s.addAttributes([
            QgsField("hh_id", QVariant.String),
            QgsField("stratum", QVariant.String),
            QgsField("food_insecure", QVariant.Int),
            QgsField("weight", QVariant.Double),
        ])
        survey_layer.updateFields()
        s_feats = []
        for i in range(40):
            f = QgsFeature(survey_layer.fields())
            x = 405000 + (i % 5) * 2000
            y = 1605000 + (i // 5) * 1500
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
            f.setAttributes([f"HH-{i+1}", "S1" if i < 20 else "S2", 1 if (i % 3 == 0) else 0, 1.25])
            s_feats.append(f)
        pr_s.addFeatures(s_feats)
        survey_layer.updateExtents()
        self.project.addMapLayer(survey_layer)

        # TOOL EXECUTION 1: design_sampling_frame
        samp_in = {
            "strata_layer": strata_layer.name(),
            "stratum_field": "stratum_id",
            "population_attribute": "population",
            "confidence": 0.95,
            "margin_of_error": 0.05,
            "plan_only": True
        }
        samp_out = design_sampling_frame(**samp_in)
        self.assertTrue(samp_out.get("success"), samp_out)
        self.assertIn("total_required", samp_out)
        self.assertGreater(samp_out["total_required"], 0)

        # TOOL EXECUTION 2: aggregate_survey_indicator
        agg_in = {
            "layer_name": survey_layer.name(),
            "group_field": "stratum",
            "indicator_field": "food_insecure",
            "kind": "proportion",
            "weight_field": "weight",
            "min_n": 10
        }
        agg_out = aggregate_survey_indicator(**agg_in)
        self.assertTrue(agg_out.get("success"), agg_out)

        # TOOL EXECUTION 3: generate_mapping_task_grid
        grid_in = {
            "aoi_layer": strata_layer.name(),
            "cell_size_m": 10000,
            "output_layer_name": "sar_task_grid"
        }
        grid_out = generate_mapping_task_grid(**grid_in)
        self.assertTrue(grid_out.get("success"), grid_out)

        # TOOL EXECUTION 4: calculate_mcda_ranking
        mcda_in = {
            "layer_name": strata_layer.name(),
            "criteria": [
                {"field": "vulnerability_idx", "weight": 0.6, "direction": "higher"},
                {"field": "access_barrier_score", "weight": 0.4, "direction": "higher"}
            ],
            "unit_name_field": "stratum_name",
            "confirmed": True
        }
        mcda_out = calculate_mcda_ranking(**mcda_in)
        self.assertTrue(mcda_out.get("success"), mcda_out)

        # Screenshot 7
        grid_layer = self.project.mapLayersByName("sar_task_grid")[0]
        screenshot_path = os.path.join(RENDERS_DIR, "screenshot_07_operational_task_grid.png")
        rendered = _render_layer_to_png([strata_layer, grid_layer, survey_layer], screenshot_path)
        self.assertTrue(rendered)

        SMOKE_EXECUTION_LOG["scenarios"].append({
            "scenario_id": "SCENARIO-HUM-07",
            "name": "Survey Sampling Frames, Cluster Aggregation, Task Grids & MCDA Prioritization",
            "tools_covered": ["design_sampling_frame", "aggregate_survey_indicator", "generate_mapping_task_grid", "calculate_mcda_ranking"],
            "inputs": {"sampling": samp_in, "survey_agg": agg_in, "grid": grid_in, "mcda": mcda_in},
            "outputs": {"sampling": samp_out, "survey_agg": agg_out, "grid": grid_out, "mcda": mcda_out},
            "screenshot": "screenshot_07_operational_task_grid.png"
        })

    # --- Scenario Family 8: Humanitarian Cartography, Dashboards & SitRep ---
    def test_scenario_08_cartography_dashboards_and_sitrep(self):
        """Scenario 8: Standard OCHA Styling, Interactive Dashboard, Spatial Report & Full SitRep Print Layout"""
        # Create presentation layer
        pub_layer = QgsVectorLayer("Polygon?crs=EPSG:32638", "marib_sitrep_districts", "memory")
        pr = pub_layer.dataProvider()
        pr.addAttributes([
            QgsField("adm2_name", QVariant.String),
            QgsField("severity_level", QVariant.Int),
            QgsField("pin_count", QVariant.Int),
        ])
        pub_layer.updateFields()
        f1 = QgsFeature(pub_layer.fields())
        f1.setGeometry(QgsGeometry.fromWkt("POLYGON((400000 1600000, 425000 1600000, 425000 1625000, 400000 1625000, 400000 1600000))"))
        f1.setAttributes(["Marib City", 4, 125000])
        f2 = QgsFeature(pub_layer.fields())
        f2.setGeometry(QgsGeometry.fromWkt("POLYGON((425000 1600000, 450000 1600000, 450000 1625000, 425000 1625000, 425000 1600000))"))
        f2.setAttributes(["Al Wadi", 5, 185000])
        pr.addFeatures([f1, f2])
        pub_layer.updateExtents()
        self.project.addMapLayer(pub_layer)

        # TOOL EXECUTION 1: apply_humanitarian_look
        look_in = {"layer_name": pub_layer.name(), "look": "severity", "field": "severity_level"}
        look_out = apply_humanitarian_look(**look_in)
        self.assertTrue(look_out.get("success"), look_out)

        # TOOL EXECUTION 2: generate_html_dashboard
        dash_in = {
            "layers": [{"layer_name": pub_layer.name()}],
            "title": "Marib Emergency Humanitarian Overview Dashboard",
            "output_path": os.path.join(OUTPUT_DIR, "marib_humanitarian_dashboard.html")
        }
        dash_out = generate_html_dashboard(**dash_in)
        self.assertTrue(dash_out.get("success"), dash_out)
        self.assertTrue(os.path.exists(dash_out["output_path"]))

        # TOOL EXECUTION 3: generate_spatial_report
        rep_in = {
            "title": "Yemen Humanitarian Situation Report",
            "insights": ["Al Wadi district reached Severity Phase 5 with 185k individuals in need.", "Immediate cluster mobilization required for WASH and Emergency Shelter."],
            "source_layers": [pub_layer.name()]
        }
        rep_out = generate_spatial_report(**rep_in)
        self.assertIn("report", rep_out)
        self.assertNotIn("error", rep_out)

        # TOOL EXECUTION 4: generate_map_product_qa_checklist
        qa_in = {"layer_name": pub_layer.name()}
        qa_out = generate_map_product_qa_checklist(**qa_in)
        self.assertTrue(qa_out.get("success"), qa_out)

        # TOOL EXECUTION 5: create_print_layout & export to high-res PNG screenshot
        layout_in = {
            "title": "Yemen: Marib Situation Report & Needs Severity",
            "page_orientation": "Landscape",
            "body_text": "Severe vulnerability detected in Al Wadi and Marib City IDP settlements. Total estimated People in Need: 310,000.",
            "zoom_to_layer": pub_layer.name(),
            "include_inset_map": False,
            "template": "standard",
            "key_figures": {"People in Need": "310,000", "Target Population": "220,000", "Partners Active": "14"}
        }
        layout_out = create_print_layout(**layout_in)
        self.assertTrue(layout_out.get("success"), layout_out)

        # Export Layout to High-Resolution Screenshot
        layout_obj = self.project.layoutManager().layoutByName(layout_out.get("layout_name"))
        if layout_obj is None:
            # Fallback to searching by prefix
            for ly in self.project.layoutManager().printLayouts():
                if "Marib" in ly.name():
                    layout_obj = ly
                    break
        self.assertIsNotNone(layout_obj)
        screenshot_path = os.path.join(RENDERS_DIR, "screenshot_08_humanitarian_sitrep_layout.png")
        exporter = QgsLayoutExporter(layout_obj)
        export_settings = QgsLayoutExporter.ImageExportSettings()
        export_settings.dpi = 150
        status = exporter.exportToImage(screenshot_path, export_settings)
        self.assertEqual(status, QgsLayoutExporter.Success)
        self.assertTrue(os.path.exists(screenshot_path) and os.path.getsize(screenshot_path) > 10000)

        SMOKE_EXECUTION_LOG["scenarios"].append({
            "scenario_id": "SCENARIO-HUM-08",
            "name": "Humanitarian Cartography, HTML Dashboard & A4 SitRep Print Layout",
            "tools_covered": ["apply_humanitarian_look", "generate_html_dashboard", "generate_spatial_report", "generate_map_product_qa_checklist", "create_print_layout"],
            "inputs": {"look": look_in, "dashboard": dash_in, "spatial_report": rep_in, "qa_checklist": qa_in, "layout": layout_in},
            "outputs": {"look": look_out, "dashboard": dash_out, "spatial_report": rep_out, "qa_checklist": qa_out, "layout": layout_out},
            "screenshot": "screenshot_08_humanitarian_sitrep_layout.png"
        })


if __name__ == "__main__":
    unittest.main()
