"""The eight argument gaps the composite-tools test found on 2026-11-22 are closed: tools that fix a number-changing choice now offer it and pass it on.

  - raster_unit (people_per_cell or people_per_km2): calculate_population_in_need and population_access_gap used to call estimate_population_exposure with the
    default only, so a density raster could not be summed correctly, and a raster whose name said density was refused with advice the tool could not follow;
  - value_forward, value_backward, value_both (what a one-way field's values mean): classify_facilities_by_access and population_access_gap used to call
    calculate_service_area with the OSM defaults only, so a field using 'F'/'T' was read wrongly.
Offline: the schemas and signatures offer the arguments, and the direction values reach calculate_service_area through the real functions with QGIS faked.
That raster_unit reaches estimate_population_exposure is pinned structurally by test_composite_tools_forward_arguments (KNOWN_GAPS is empty). Not run against
a real density raster or a real one-way road layer in QGIS."""
import inspect
import types
import unittest
from unittest.mock import MagicMock, patch

from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
from cartogen_ai.core.agent.tools import analysis_tools, logistics_tools

_POLYGONS = types.SimpleNamespace(geometryType=lambda _wkb: "polygon", GeometryType=types.SimpleNamespace(PolygonGeometry="polygon"))
DIRECTION = ("value_forward", "value_backward", "value_both")


def _schema(name):
    return next(t["function"]["parameters"]["properties"] for t in TOOLS_SCHEMA if t["function"]["name"] == name)


class TestSchemasAndSignaturesOfferTheArguments(unittest.TestCase):
    def test_raster_unit_is_offered_by_both_population_composites(self):
        for tool, fn in (("calculate_population_in_need", analysis_tools.calculate_population_in_need),
                         ("population_access_gap", logistics_tools.population_access_gap)):
            self.assertIn("raster_unit", _schema(tool), tool)
            self.assertEqual(inspect.signature(fn).parameters["raster_unit"].default, "people_per_cell", tool)

    def test_the_direction_values_are_offered_by_both_access_composites_with_the_osm_defaults(self):
        for tool, fn in (("classify_facilities_by_access", logistics_tools.classify_facilities_by_access),
                         ("population_access_gap", logistics_tools.population_access_gap)):
            for name, default in zip(DIRECTION, ("yes", "-1", "no"), strict=True):
                self.assertIn(name, _schema(tool), (tool, name))
                self.assertEqual(inspect.signature(fn).parameters[name].default, default, (tool, name))


class TestTheDirectionValuesReachTheServiceAreaCall(unittest.TestCase):
    def _captured(self, fn, **kwargs):
        seen = {}

        def fake_service(*args, **kw):
            seen.update(kw)
            return {"error": "stop here"}
        with patch.object(logistics_tools, "QGIS_AVAILABLE", True), patch.object(logistics_tools, "calculate_service_area", fake_service), \
             patch.object(logistics_tools, "_find_layer_by_name", lambda name: MagicMock()), \
             patch.object(logistics_tools, "QgsWkbTypes", _POLYGONS, create=True):
            result = fn(**kwargs)
        self.assertEqual(result, {"error": "stop here"})
        return seen

    def test_classify_facilities_by_access_passes_them_on(self):
        seen = self._captured(logistics_tools.classify_facilities_by_access, origin_layer="o", facility_layer="f", road_network_layer="r", travel_cost=1000,
                              direction_field="oneway", value_forward="F", value_backward="T", value_both="B")
        self.assertEqual((seen["value_forward"], seen["value_backward"], seen["value_both"]), ("F", "T", "B"))

    def test_population_access_gap_passes_them_on(self):
        seen = self._captured(logistics_tools.population_access_gap, facility_layer="f", road_network_layer="r", population_raster_layer="p", area_layer="a",
                              travel_cost=1000, direction_field="oneway", value_forward="F", value_backward="T", value_both="B")
        self.assertEqual((seen["value_forward"], seen["value_backward"], seen["value_both"]), ("F", "T", "B"))

    def test_the_defaults_are_still_the_osm_values(self):
        seen = self._captured(logistics_tools.classify_facilities_by_access, origin_layer="o", facility_layer="f", road_network_layer="r", travel_cost=1000)
        self.assertEqual((seen["value_forward"], seen["value_backward"], seen["value_both"]), ("yes", "-1", "no"))


if __name__ == "__main__":
    unittest.main()
