"""#154: the DEM's vertical unit is explicit, not assumed."""
import unittest
from unittest import mock

from cartogen_ai.core.agent.tools import impedance_tools
from cartogen_ai.core.agent.tools.raster_tools import vertical_unit_factor


class _Provider:
    def __init__(self, a, b):
        self.values = iter([a, b])

    def sample(self, point, band):
        return next(self.values), True


class _Dem:
    def __init__(self, a, b):
        self._p = _Provider(a, b)

    def dataProvider(self):
        return self._p


class _Pt:
    def x(self):
        return 0.0

    def y(self):
        return 0.0


@mock.patch.object(impedance_tools, "QgsPointXY", lambda x, y: (x, y), create=True)     # QGIS is not importable offline
class TestVerticalUnit(unittest.TestCase):
    def test_known_units(self):
        self.assertEqual(vertical_unit_factor("m"), 1.0)
        self.assertEqual(vertical_unit_factor(None), 1.0)
        self.assertAlmostEqual(vertical_unit_factor("ft"), 0.3048)
        self.assertAlmostEqual(vertical_unit_factor(" US_FT "), 1200 / 3937)
        self.assertIsNone(vertical_unit_factor("furlongs"))

    def test_slope_penalty_is_physical_whatever_the_dem_unit(self):
        """A 100 m rise over 1000 m, once as metres and once as feet (328.084 ft), must cost the same."""
        in_metres = impedance_tools._slope_penalty(_Dem(0.0, 100.0), _Pt(), _Pt(), 1000.0, vertical_unit_factor("m"))
        in_feet = impedance_tools._slope_penalty(_Dem(0.0, 100.0 / 0.3048), _Pt(), _Pt(), 1000.0, vertical_unit_factor("ft"))
        self.assertAlmostEqual(in_metres, in_feet)
        wrong = impedance_tools._slope_penalty(_Dem(0.0, 100.0 / 0.3048), _Pt(), _Pt(), 1000.0, 1.0)
        self.assertLess(wrong, in_metres, "feet read as metres would overstate the slope")


if __name__ == "__main__":
    unittest.main()
