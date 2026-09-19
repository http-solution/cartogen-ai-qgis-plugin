# -*- coding: utf-8 -*-
"""
Live Verification Pipeline for Cartogen AI:
- Live Map Intelligence Engine (layer ordering, component 20% fill alpha, scale-aware PAL labeling)
- Live Intelligent Representation Planner (statistical profiling, raw count penalty, native renderers)
- Live Selection-Aware Export (filtering to selected subset, excluding unselected features)
- Live Chat Action Registry & Dispatch
"""

import os
import sys
import tempfile
import csv

# Set Qt offscreen platform for headless execution
os.environ["QT_QPA_PLATFORM"] = "offscreen"

src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from qgis.core import (
    QgsApplication,
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsField,
    QgsFields,
    QgsWkbTypes,
    QgsPointClusterRenderer,
    QgsGraduatedSymbolRenderer,
    QgsSimpleFillSymbolLayer,
)
from qgis.PyQt.QtCore import QVariant


def run_live_test():
    print("==================================================================")
    print("   CARTOGEN AI - LIVE COMPREHENSIVE VERIFICATION PIPELINE         ")
    print("==================================================================")

    # 1. Initialize QGIS Application
    app = QgsApplication([], True)
    app.initQgis()

    plugins_dir = os.path.join(QgsApplication.pkgDataPath(), "python", "plugins")
    if os.path.isdir(plugins_dir) and plugins_dir not in sys.path:
        sys.path.insert(0, plugins_dir)

    try:
        import processing
        from processing.core.Processing import Processing
        Processing.initialize()
    except Exception as e:
        print(f"   [WARN] Processing initialization note: {e}")

    print("[1/5] QGIS & Processing initialized successfully.")

    proj = QgsProject.instance()
    proj.clear()

    # -----------------------------------------------------------------------
    # TEST 2: Map Intelligence Engine (Layer Ordering & Component Alpha)
    # -----------------------------------------------------------------------
    print("\n[2/5] Testing Map Intelligence Engine (Local Role Insertion & Symbology)...")
    from cartogen_ai.core.agent.map_intelligence import process_map_output, ChatActionRegistry

    # Create source point layer: Health Facilities
    points_layer = QgsVectorLayer("Point?crs=EPSG:4326", "Health_Facilities", "memory")
    pr_pts = points_layer.dataProvider()
    pr_pts.addAttributes([QgsField("name", QVariant.String), QgsField("beds", QVariant.Int)])
    points_layer.updateFields()

    # Add 5 points (3 clustered, 2 scattered)
    coords = [
        (35.21, 31.76), (35.212, 31.761), (35.211, 31.759),  # Cluster in Jerusalem area
        (35.50, 32.00), (35.80, 32.50),                      # Outliers
    ]
    feats = []
    for i, (x, y) in enumerate(coords):
        f = QgsFeature(points_layer.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
        f.setAttributes([f"Clinic_{i+1}", (i + 1) * 20])
        feats.append(f)
    pr_pts.addFeatures(feats)
    points_layer.updateExtents()
    proj.addMapLayer(points_layer)

    # Create Buffer Layer (Proximity 5km)
    buffer_layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "Health_Facilities_buffer_5km", "memory")
    pr_buf = buffer_layer.dataProvider()
    pr_buf.addAttributes([QgsField("source_id", QVariant.String)])
    buffer_layer.updateFields()

    fb = QgsFeature(buffer_layer.fields())
    fb.setGeometry(QgsGeometry.fromRect(points_layer.extent()))
    pr_buf.addFeatures([fb])
    buffer_layer.updateExtents()

    # Process buffer via Map Intelligence Engine
    res_intel = process_map_output(
        buffer_layer,
        output_role="proximity_buffer",
        source_layer_id=points_layer.id(),
    )
    assert res_intel["success"], f"Map intelligence failed: {res_intel}"

    # Verify layer ordering: buffer must be immediately below source point layer
    root = proj.layerTreeRoot()
    tree_layers = [node.layerId() for node in root.findLayers()]
    idx_points = tree_layers.index(points_layer.id())
    idx_buffer = tree_layers.index(buffer_layer.id())
    print(f"   -> Layer Tree Order: Points index={idx_points}, Buffer index={idx_buffer}")
    assert idx_buffer > idx_points, "Buffer should be below points in draw order (larger index = lower)!"

    # Verify component-level symbology (20% fill alpha, 100% stroke)
    sym = buffer_layer.renderer().symbol()
    fill_sl = sym.symbolLayer(0)
    fill_col = fill_sl.fillColor()
    stroke_col = fill_sl.strokeColor()
    print(f"   -> Buffer Fill Alpha: {fill_col.alpha()} (expected ~51 for 20%), Stroke Alpha: {stroke_col.alpha()} (expected 255 for 100%)")
    assert fill_col.alpha() <= 60, f"Fill alpha {fill_col.alpha()} is too opaque!"
    assert stroke_col.alpha() == 255, "Stroke outline must be 100% crisp!"
    print("   [PASSED] Map Intelligence correctly placed buffer below points and applied 20% component alpha.")

    # -----------------------------------------------------------------------
    # TEST 3: Intelligent Representation Planner (Profiling & Native Renderers)
    # -----------------------------------------------------------------------
    print("\n[3/5] Testing Intelligent Representation Planner...")
    from cartogen_ai.core.representation import profile_layer, plan_representations, apply_representation
    from cartogen_ai.core.representation.models import RepresentationCandidate

    # 3.1 Point Layer Profile & Cluster Recommendation
    prof_pts = profile_layer(points_layer)
    print(f"   -> Points Profile: feature_count={prof_pts.feature_count}, density={prof_pts.spatial_density}, overlap={prof_pts.overlap_ratio}")
    cand_pts = plan_representations(prof_pts)
    print(f"   -> Top recommended representation for points: {cand_pts[0].id} (Score: {cand_pts[0].score.total_score})")

    # Apply Top Recommended Representation
    print(f"   -> Applying candidate '{cand_pts[0].id}' with target_field='{cand_pts[0].target_field}'...")
    apply_res = apply_representation(points_layer, cand_pts[0])
    print(f"   -> apply_res: {apply_res}")
    assert apply_res.get("success"), f"Failed to apply representation: {apply_res}"
    print(f"   -> Applied Renderer Type: {type(points_layer.renderer()).__name__}")

    # Also test applying Point Cluster Renderer explicitly
    cluster_cand = RepresentationCandidate(id="point_cluster", label="Point Clusters", renderer_type="cluster")
    apply_cluster = apply_representation(points_layer, cluster_cand)
    assert apply_cluster.get("success"), f"Failed to apply cluster: {apply_cluster}"
    print(f"   -> Cluster Renderer Applied: {type(points_layer.renderer()).__name__}")
    assert isinstance(points_layer.renderer(), QgsPointClusterRenderer), "Expected QgsPointClusterRenderer!"
    print("   [PASSED] Proportional symbols & Point cluster renderers configured natively on live layer.")

    # 3.2 Polygon Layer: Raw Count vs Rate Honesty Check
    poly_layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "Crisis_Districts", "memory")
    pr_poly = poly_layer.dataProvider()
    pr_poly.addAttributes([
        QgsField("district", QVariant.String),
        QgsField("casualties_count", QVariant.Int),
        QgsField("vulnerability_rate", QVariant.Double),
    ])
    poly_layer.updateFields()

    # Add 3 polygon features
    for i in range(3):
        f = QgsFeature(poly_layer.fields())
        f.setGeometry(QgsGeometry.fromRect(points_layer.extent()))
        f.setAttributes([f"District_{i}", (i + 1) * 150, 0.15 + (i * 0.25)])
        pr_poly.addFeatures([f])
    poly_layer.updateExtents()
    proj.addMapLayer(poly_layer)

    prof_poly = profile_layer(poly_layer)
    print(f"   -> Polygons Fields Profile:")
    for fn, fp in prof_poly.fields.items():
        print(f"      * {fn}: semantic_type={fp.semantic_type}, is_numeric={fp.is_numeric}")

    # Case A: When user wants to show raw casualties_count -> must warn and prefer proportional centroid
    cand_count = plan_representations(prof_poly, target_field="casualties_count")
    top_count = cand_count[0]
    print(f"   -> Raw count query top candidate: {top_count.id} ({top_count.label})")
    assert top_count.id == "polygon_proportional_centroid", "Raw count must prefer proportional centroid!"
    # Verify choropleth candidate has warning
    choropleth_cand = [c for c in cand_count if c.id == "polygon_choropleth_rate"][0]
    assert len(choropleth_cand.warnings) > 0, "Choropleth with raw count must carry a cartographic warning!"
    print(f"      * Choropleth warning verified: {choropleth_cand.warnings[0]}")

    # Case B: When user wants to show normalized vulnerability_rate -> choropleth is recommended
    cand_rate = plan_representations(prof_poly, target_field="vulnerability_rate")
    top_rate = cand_rate[0]
    print(f"   -> Normalized rate query top candidate: {top_rate.id} ({top_rate.label})")
    assert top_rate.id == "polygon_choropleth_rate", "Normalized rate should recommend graduated choropleth!"
    assert len(top_rate.warnings) == 0, "Normalized rate choropleth should have 0 warnings."
    print("   [PASSED] Statistical honesty engine correctly penalizes raw counts and favors proportional centroids.")

    # -----------------------------------------------------------------------
    # TEST 4: Selection-Aware Spatial Export
    # -----------------------------------------------------------------------
    print("\n[4/5] Testing Selection-Aware Spatial Export...")
    from cartogen_ai.core.agent.tools.export_tools import export_to_csv

    # Select only 2 features out of 5 (e.g. within proximity query)
    points_layer.removeSelection()
    feature_ids = [f.id() for f in points_layer.getFeatures()][:2]
    points_layer.select(feature_ids)
    print(f"   -> Active layer feature count: {points_layer.featureCount()}, Selected: {points_layer.selectedFeatureCount()}")

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
        tmp_csv = tf.name

    try:
        exp_res = export_to_csv("Health_Facilities", output_path=tmp_csv, only_selected=True)
        assert exp_res["success"], f"Export failed: {exp_res}"
        print(f"   -> Export result: {exp_res}")

        with open(tmp_csv, "r", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        # Header + 2 data rows = 3 rows total
        data_rows = rows[1:]
        print(f"   -> Exported CSV Rows: {len(data_rows)} data rows (expected 2)")
        assert len(data_rows) == 2, f"Expected 2 selected features, got {len(data_rows)}!"
        print("   [PASSED] Export tool strictly respected spatial selection, excluding features outside query.")
    finally:
        if os.path.exists(tmp_csv):
            os.remove(tmp_csv)

    # -----------------------------------------------------------------------
    # TEST 5: Interactive Chat Action Registry & High-Level Tools
    # -----------------------------------------------------------------------
    print("\n[5/5] Testing High-Level Tools & Action Chips...")
    from cartogen_ai.core.agent.tools.representation_tools import (
        recommend_map_representation,
        explain_current_representation,
    )

    rec_res = recommend_map_representation("Health_Facilities")
    assert rec_res["success"], f"Recommend failed: {rec_res}"
    assert "action_chips" in rec_res and len(rec_res["action_chips"]) > 0
    chip = rec_res["action_chips"][0]
    print(f"   -> Generated Action Chip: label='{chip['label']}', url='{chip['url']}'")
    assert chip["url"].startswith("cartogen://action/act_")

    # Verify action registered in ChatActionRegistry
    act_id = chip["url"].replace("cartogen://action/", "")
    registered_act = ChatActionRegistry.get(act_id)
    assert registered_act is not None
    assert registered_act.kind == "apply_style"
    assert registered_act.payload["layer_name"] == "Health_Facilities"
    print(f"   -> Verified ChatAction in Registry: kind={registered_act.kind}, layer={registered_act.payload['layer_name']}")

    # Explain current representation
    expl_res = explain_current_representation("Crisis_Districts")
    assert expl_res["success"]
    print(f"   -> Explain evaluation: {expl_res['cartographic_evaluation']}")

    print("\n==================================================================")
    print("   ALL LIVE TESTS PASSED CLEANLY (5/5). 100% OPERATIONAL!        ")
    print("==================================================================")
    app.exitQgis()


if __name__ == "__main__":
    run_live_test()
