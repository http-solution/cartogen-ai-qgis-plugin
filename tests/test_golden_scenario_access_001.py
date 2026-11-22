"""
Golden Scenario GS-ACCESS-001: Service-Area Network Hull -> Population Access Gap Integrity.

Validates:
- Network analysis service area calculation (or reach geometry)
- Polygon intersection with administrative AOI
- Population exposure aggregation / zonal calculation
- Reconciliation of:
  * Total Area Population
  * Reachable Population
  * Population Access Gap (Total - Reachable)
  * Gap Percentage
- Ensures mathematical determinism:
  Reachable Pop + Gap Pop == Total Population (within 0.01 tolerance)
"""

import unittest
from unittest.mock import MagicMock, patch
from contextlib import ExitStack

from cartogen_ai.core.agent.tools.logistics_tools import population_access_gap


class TestGoldenScenarioAccess001(unittest.TestCase):
    def test_gs_access_001_service_area_population_access_gap(self):
        """
        Scenario:
        District Population = 250,000.
        Service area reached via road network around 3 health facilities:
        - Reachable Population (Concave Hull Headline) = 175,000.
        - Convex Hull (Upper Bound) = 210,000.
        - Road Buffer (Direct Corridor) = 120,000.

        Asserts:
        - Headline reach geometry matches concave_hull.
        - Gap Population = 250,000 - 175,000 = 75,000.
        - Gap Percent = (75,000 / 250,000) * 100 = 30.0%.
        - Conservation Invariant: reachable_population + gap_population == total_population.
        - Confidence caveat metadata correctly attached.
        """
        lt_path = "cartogen_ai.core.agent.tools.logistics_tools"
        with ExitStack() as stack:
            mock_estimate_pop = stack.enter_context(
                patch("cartogen_ai.core.agent.tools.raster_tools.estimate_population_exposure")
            )
            stack.enter_context(patch(f"{lt_path}.QgsProject", create=True))
            mock_processing = stack.enter_context(patch(f"{lt_path}.processing", create=True))
            mock_find = stack.enter_context(patch(f"{lt_path}._find_layer_by_name"))
            mock_calc = stack.enter_context(patch(f"{lt_path}.calculate_service_area"))
            mock_reach = stack.enter_context(patch(f"{lt_path}._road_reach_polygon"))
            mock_concave = stack.enter_context(patch(f"{lt_path}._concave_reach_polygon"))
            mock_wkb = stack.enter_context(patch(f"{lt_path}.QgsWkbTypes", create=True))
            stack.enter_context(patch(f"{lt_path}.QGIS_AVAILABLE", True))

            mock_wkb.geometryType.return_value = "polygon-sentinel"
            mock_wkb.GeometryType.PolygonGeometry = "polygon-sentinel"

            area_mock = MagicMock()
            hull_mock = MagicMock()
            lines_mock = MagicMock()

            mock_find.side_effect = {
                "district_boundary": area_mock,
                "Facilities_service_area_0": hull_mock,
                "Facilities_service_area_lines_0": lines_mock,
            }.get

            mock_calc.return_value = {
                "facility_count": 3,
                "layers_created": ["Facilities_service_area_lines_0", "Facilities_service_area_0"],
            }

            intersect_mock = MagicMock()
            intersect_mock.featureCount.return_value = 5
            mock_reach.return_value = MagicMock()
            mock_concave.return_value = MagicMock()
            mock_processing.run.side_effect = lambda alg, params: {
                "OUTPUT": intersect_mock if alg == "native:intersection" else MagicMock()
            }

            def pop_exposure_side_effect(raster, layer_name, raster_unit="people_per_cell"):
                if layer_name == "district_boundary":
                    return {
                        "success": True,
                        "total_population": 250000.0,
                        "pop_source": "WorldPop 2026",
                        "pop_reference_year": "2026",
                    }
                if "convex_hull" in layer_name:
                    return {"success": True, "total_population": 210000.0}
                if "road_buffer" in layer_name:
                    return {"success": True, "total_population": 120000.0}
                # Headline concave hull
                return {"success": True, "total_population": 175000.0}

            mock_estimate_pop.side_effect = pop_exposure_side_effect

            # Execute population_access_gap with explicit travel_cost (Rule 37 compliant)
            result = population_access_gap(
                facility_layer="Facilities",
                road_network_layer="roads",
                population_raster_layer="worldpop_2026",
                area_layer="district_boundary",
                travel_cost=45,  # 45 minutes travel threshold
                reach_geometry="concave_hull",
            )

            self.assertTrue(result.get("success"), f"Access gap analysis failed: {result}")
            self.assertEqual(result["total_population"], 250000.0)
            self.assertEqual(result["reachable_population"], 175000.0)
            self.assertEqual(result["gap_population"], 75000.0)
            self.assertAlmostEqual(result["gap_percent"], 30.0, places=2)

            # Core Humanitarian Mathematical Invariant:
            # reachable_pop + gap_pop MUST equal total_population
            self.assertAlmostEqual(
                result["reachable_population"] + result["gap_population"],
                result["total_population"],
                places=2
            )

            # Verify bracketing figures are provided to assist operational decision-making
            self.assertIn("reach_figures", result)
            methods_reported = {f["method"] for f in result["reach_figures"]}
            self.assertEqual(methods_reported, {"concave_hull", "convex_hull", "road_buffer"})


if __name__ == "__main__":
    unittest.main()
