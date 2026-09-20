# -*- coding: utf-8 -*-
"""Unit tests for the Intelligent Representation Planner and representation tools."""

import unittest
from unittest.mock import MagicMock, patch

from cartogen_ai.core.representation.models import (
    FieldSemanticProfile,
    LayerSemanticProfile,
)
from cartogen_ai.core.representation.profiler import profile_layer
from cartogen_ai.core.representation.planner import plan_representations
from cartogen_ai.core.agent.tools.representation_tools import (
    analyze_layer_for_visualization,
    recommend_map_representation,
    apply_recommended_representation,
    explain_current_representation,
)
from cartogen_ai.core.agent.tools.registry import TOOL_REGISTRY


class TestRepresentationProfiler(unittest.TestCase):
    def test_profile_point_layer(self):
        mock_layer = MagicMock()
        mock_layer.name.return_value = "Health_Clinics"
        mock_layer.isValid.return_value = True
        mock_layer.geometryType.return_value = 0  # Point
        mock_layer.featureCount.return_value = 450

        # Mock fields
        f1 = MagicMock()
        f1.name.return_value = "facility_name"
        f1.isNumeric.return_value = False
        f1.typeName.return_value = "String"

        f2 = MagicMock()
        f2.name.return_value = "bed_count"
        f2.isNumeric.return_value = True
        f2.typeName.return_value = "Integer"

        f3 = MagicMock()
        f3.name.return_value = "occupancy_rate"
        f3.isNumeric.return_value = True
        f3.typeName.return_value = "Real"

        mock_layer.fields.return_value = [f1, f2, f3]

        # Mock features with values
        feat1 = MagicMock()
        feat1.geometry.return_value.isEmpty.return_value = False
        feat1.geometry.return_value.boundingBox.return_value = MagicMock()
        data1 = {"facility_name": "Clinic A", "bed_count": 25, "occupancy_rate": 0.75}
        feat1.__getitem__.side_effect = lambda k: data1.get(k)

        feat2 = MagicMock()
        feat2.geometry.return_value.isEmpty.return_value = False
        feat2.geometry.return_value.boundingBox.return_value = MagicMock()
        data2 = {"facility_name": "Clinic B", "bed_count": 80, "occupancy_rate": 0.92}
        feat2.__getitem__.side_effect = lambda k: data2.get(k)

        mock_layer.getFeatures.return_value = [feat1, feat2]

        prof = profile_layer(mock_layer)
        self.assertEqual(prof.layer_name, "Health_Clinics")
        self.assertEqual(prof.geometry, "point")
        self.assertEqual(prof.feature_count, 450)
        self.assertIn("facility_name", prof.fields)
        self.assertIn("bed_count", prof.fields)
        self.assertIn("occupancy_rate", prof.fields)

        self.assertEqual(prof.fields["facility_name"].semantic_type, "nominal")
        self.assertEqual(prof.fields["bed_count"].semantic_type, "positive_quantity")
        self.assertEqual(prof.fields["occupancy_rate"].semantic_type, "rate_percentage")

    def test_all_negative_field_is_not_misclassified_as_positive_quantity(self):
        # Real bug found in a code-review pass (2026-09-20): the "raw count" check used
        # `all(v.is_integer() for v in numeric_values if v >= 0)` -- for a field with ONLY
        # negative fractional values, the filtered generator is empty, and Python's all() on
        # an empty iterable is vacuously True, so the field was wrongly classified
        # "positive_quantity" despite being entirely negative.
        mock_layer = MagicMock()
        mock_layer.name.return_value = "Terrain_Points"
        mock_layer.isValid.return_value = True
        mock_layer.geometryType.return_value = 0
        mock_layer.featureCount.return_value = 3

        f1 = MagicMock()
        f1.name.return_value = "depth_change"
        f1.isNumeric.return_value = True
        f1.typeName.return_value = "Real"
        mock_layer.fields.return_value = [f1]

        values = [-1.5, -2.3, -10.7]
        feats = []
        for v in values:
            feat = MagicMock()
            feat.geometry.return_value.isEmpty.return_value = False
            feat.geometry.return_value.boundingBox.return_value = MagicMock()
            feat.__getitem__.side_effect = (lambda val: (lambda k: val if k == "depth_change" else None))(v)
            feats.append(feat)
        mock_layer.getFeatures.return_value = feats

        prof = profile_layer(mock_layer)
        self.assertEqual(prof.fields["depth_change"].semantic_type, "nominal")


class TestRepresentationPlanner(unittest.TestCase):
    def test_point_dense_recommends_cluster_or_heatmap(self):
        prof = LayerSemanticProfile(
            layer_name="Shelters_Dense",
            layer_type="vector",
            geometry="point",
            feature_count=1200,
            spatial_density="high",
            overlap_ratio=0.35,
            crs_authid="EPSG:4326",
            fields={},
        )
        candidates = plan_representations(prof)
        self.assertGreater(len(candidates), 0)
        top_cand = candidates[0]
        self.assertIn(top_cand.id, ["point_cluster", "point_heatmap"])
        self.assertGreaterEqual(top_cand.score.total_score, 0.7)

    def test_polygon_raw_count_penalizes_choropleth(self):
        prof = LayerSemanticProfile(
            layer_name="Admin2_Casualties",
            layer_type="vector",
            geometry="polygon",
            feature_count=45,
            spatial_density="low",
            overlap_ratio=0.0,
            crs_authid="EPSG:4326",
            fields={
                "total_affected": FieldSemanticProfile(
                    name="total_affected",
                    semantic_type="positive_quantity",
                    is_numeric=True,
                )
            },
        )
        candidates = plan_representations(prof, target_field="total_affected")
        top_cand = candidates[0]
        # Proportional centroid should be preferred over raw count choropleth
        self.assertEqual(top_cand.id, "polygon_proportional_centroid")
        # Ensure any raw count choropleth candidate has a warning
        for c in candidates:
            if c.id == "polygon_choropleth_rate":
                self.assertGreater(len(c.warnings), 0)
                self.assertTrue(any("misleading" in w.lower() or "choropleth" in w.lower() for w in c.warnings))

    def test_polygon_rate_prefers_choropleth(self):
        prof = LayerSemanticProfile(
            layer_name="Admin2_Vulnerability",
            layer_type="vector",
            geometry="polygon",
            feature_count=45,
            spatial_density="low",
            overlap_ratio=0.0,
            crs_authid="EPSG:4326",
            fields={
                "poverty_rate": FieldSemanticProfile(
                    name="poverty_rate",
                    semantic_type="rate_percentage",
                    is_numeric=True,
                    min_value=0.05,
                    max_value=0.82,
                )
            },
        )
        candidates = plan_representations(prof, target_field="poverty_rate")
        top_cand = candidates[0]
        self.assertEqual(top_cand.id, "polygon_choropleth_rate")
        self.assertEqual(len(top_cand.warnings), 0)


class TestRepresentationTools(unittest.TestCase):
    def test_tools_registered(self):
        self.assertIn("analyze_layer_for_visualization", TOOL_REGISTRY)
        self.assertIn("recommend_map_representation", TOOL_REGISTRY)
        self.assertIn("apply_recommended_representation", TOOL_REGISTRY)
        self.assertIn("explain_current_representation", TOOL_REGISTRY)

    @patch("cartogen_ai.core.agent.tools.representation_tools._get_layer")
    def test_recommend_map_representation_returns_action_chips(self, mock_get_layer):
        mock_layer = MagicMock()
        mock_layer.name.return_value = "Displacement_Sites"
        mock_layer.isValid.return_value = True
        mock_layer.geometryType.return_value = 0  # Point
        mock_layer.featureCount.return_value = 600
        mock_layer.fields.return_value = []
        mock_layer.getFeatures.return_value = []
        mock_get_layer.return_value = mock_layer

        res = recommend_map_representation("Displacement_Sites")
        self.assertTrue(res.get("success"))
        self.assertIn("recommended", res)
        self.assertIn("action_chips", res)
        chips = res["action_chips"]
        self.assertGreater(len(chips), 0)
        self.assertTrue(chips[0]["url"].startswith("cartogen://action/act_"))

    @patch("cartogen_ai.core.agent.tools.representation_tools._get_layer")
    def test_analyze_layer_for_visualization(self, mock_get_layer):
        mock_layer = MagicMock()
        mock_layer.name.return_value = "Admin_Boundaries"
        mock_layer.isValid.return_value = True
        mock_layer.geometryType.return_value = 2  # Polygon
        mock_layer.featureCount.return_value = 25
        mock_layer.fields.return_value = []
        mock_layer.getFeatures.return_value = []
        mock_get_layer.return_value = mock_layer

        res = analyze_layer_for_visualization("Admin_Boundaries")
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("geometry"), "polygon")
        self.assertEqual(res.get("feature_count"), 25)

    @patch("cartogen_ai.core.agent.tools.representation_tools._get_layer")
    def test_explain_current_representation_detects_raw_count_choropleth(self, mock_get_layer):
        mock_layer = MagicMock()
        mock_layer.name.return_value = "Districts"
        mock_layer.isValid.return_value = True
        mock_layer.geometryType.return_value = 2  # Polygon
        mock_layer.featureCount.return_value = 10

        # Simulate Graduated renderer on a raw count field
        mock_renderer = MagicMock()
        type(mock_renderer).__name__ = "QgsGraduatedSymbolRenderer"
        mock_layer.renderer.return_value = mock_renderer

        f1 = MagicMock()
        f1.name.return_value = "casualties_total"
        f1.isNumeric.return_value = True
        f1.typeName.return_value = "Integer"
        mock_layer.fields.return_value = [f1]

        feat = MagicMock()
        feat.geometry.return_value.isEmpty.return_value = False
        feat.__getitem__.side_effect = lambda k: 120
        mock_layer.getFeatures.return_value = [feat]

        mock_get_layer.return_value = mock_layer

        res = explain_current_representation("Districts")
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("cartographic_evaluation"), "Suboptimal")
        self.assertGreater(len(res.get("issues_and_recommendations", [])), 0)
        self.assertTrue(any("raw count" in iss.lower() for iss in res["issues_and_recommendations"]))

    @patch("cartogen_ai.core.agent.tools.representation_tools.apply_representation")
    @patch("cartogen_ai.core.agent.tools.representation_tools._get_layer")
    def test_apply_recommended_representation_dispatches_candidate(self, mock_get_layer, mock_apply_rep):
        mock_layer = MagicMock()
        mock_layer.name.return_value = "Refugee_Camps"
        mock_get_layer.return_value = mock_layer
        mock_apply_rep.return_value = {"success": True, "layer_name": "Refugee_Camps", "applied": "point_cluster"}

        res = apply_recommended_representation("Refugee_Camps", "point_cluster")
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("applied"), "point_cluster")
        mock_apply_rep.assert_called_once()


if __name__ == "__main__":
    unittest.main()
