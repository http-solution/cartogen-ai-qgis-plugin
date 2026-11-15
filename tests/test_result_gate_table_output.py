"""Round-2 live run 2026-11-05, row E4: a Processing algorithm that writes a TABLE (native:basicstatisticsforfields) got the check
"1 of 1 geometries (100%) are invalid or empty" -> FAIL, and the model was told to call a correct result wrong. A layer with no geometry
has nothing to check. Offline: `qgis.core` is replaced by a stub, the layer is a fake."""
import sys
import types
import unittest
from unittest.mock import patch

from cartogen_ai.core.agent import result_gate
from cartogen_ai.core.validators import result_checks


class _Geom:
    def __init__(self, empty=False, valid=True):
        self._empty, self._valid = empty, valid

    def isNull(self):
        return False

    def isEmpty(self):
        return self._empty

    def isGeosValid(self):
        return self._valid


class _Feature:
    def __init__(self, geometry):
        self._geometry = geometry

    def geometry(self):
        return self._geometry

    def __getitem__(self, name):
        return 1


class _Fields:
    def indexOf(self, name):
        return 0


class _Crs:
    def isValid(self):
        return False


class _Layer:
    def __init__(self, features, spatial):
        self._features, self._spatial = features, spatial

    def isSpatial(self):
        return self._spatial

    def crs(self):
        return _Crs()

    def featureCount(self):
        return len(self._features)

    def fields(self):
        return _Fields()

    def name(self):
        return "layer"

    def getFeatures(self, _request):
        return iter(self._features)


class _Request:
    def setLimit(self, _n):
        return self


def summarize(layer):
    stub = types.ModuleType("qgis.core")
    stub.QgsFeatureRequest = _Request
    with patch.dict(sys.modules, {"qgis": types.ModuleType("qgis"), "qgis.core": stub}):
        return result_gate.summarize_layer(layer, [])[0]


class TestTableOutputsHaveNoGeometryCheck(unittest.TestCase):
    def test_a_table_row_is_not_an_empty_geometry(self):
        summary = summarize(_Layer([_Feature(None)], spatial=False))
        self.assertIsNone(summary["geometry"])
        self.assertEqual(summary["feature_count"], 1)

    def test_the_checks_then_skip_geometry_instead_of_failing_it(self):
        summary = summarize(_Layer([_Feature(None)], spatial=False))
        ids = [c["id"] for c in result_checks.run_checks(summary, {})]
        self.assertNotIn("geometry", ids)
        self.assertEqual(result_checks.summarize(result_checks.run_checks(summary, {}))[1], [])      # nothing failed

    def test_a_spatial_layer_with_an_empty_geometry_still_warns_or_fails(self):
        summary = summarize(_Layer([_Feature(_Geom(empty=True))], spatial=True))
        self.assertEqual(summary["geometry"], {"total": 1, "invalid": 0, "empty": 1})
        check = result_checks.check_geometry(summary, {})
        self.assertEqual(check["status"], result_checks.FAIL)

    def test_a_spatial_layer_with_valid_geometries_passes(self):
        summary = summarize(_Layer([_Feature(_Geom()), _Feature(_Geom())], spatial=True))
        self.assertEqual(result_checks.check_geometry(summary, {})["status"], result_checks.PASS)


if __name__ == "__main__":
    unittest.main()
