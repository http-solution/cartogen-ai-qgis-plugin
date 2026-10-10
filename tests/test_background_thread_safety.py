# -*- coding: utf-8 -*-
"""Which Processing algorithms may run on the background task runner (PR #249 / #251: gdal:slope crashed the live CI job there)."""
import unittest

from cartogen_ai.core.agent.tools import _background_processing as bp


class TestIsThreadSafeAlgorithm(unittest.TestCase):
    def test_native_algorithms_are_allowed(self):
        for alg in ("native:buffer", "native:zonalstatisticsfb", "native:serviceareafrompoint"):
            self.assertTrue(bp.is_thread_safe_algorithm(alg), alg)

    def test_python_implemented_algorithms_are_not(self):
        for alg in ("gdal:slope", "gdal:rastercalculator", "qgis:heatmapkerneldensityestimation", "script:anything", ""):
            self.assertFalse(bp.is_thread_safe_algorithm(alg), alg)


if __name__ == "__main__":
    unittest.main()
