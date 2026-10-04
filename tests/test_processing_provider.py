# -*- coding: utf-8 -*-
import unittest
from unittest.mock import MagicMock

from cartogen_ai.processing.provider import (
    CartogenProcessingProvider,
    OptimalHubSitingAlgorithm,
    CalculateServiceAreaAlgorithm,
    QGIS_PROCESSING_AVAILABLE,
)


class TestProcessingProvider(unittest.TestCase):
    def test_provider_metadata(self):
        provider = CartogenProcessingProvider()
        self.assertEqual(provider.id(), "cartogen")
        self.assertEqual(provider.name(), "Cartogen AI")
        self.assertEqual(provider.longName(), "Cartogen AI Spatial Algorithms")

    def test_optimal_hub_siting_algorithm_metadata(self):
        alg = OptimalHubSitingAlgorithm()
        self.assertEqual(alg.name(), "optimalhubsiting")
        self.assertEqual(alg.groupId(), "logistics")
        self.assertIn("Optimal Hub Siting", alg.displayName())
        clone = alg.createInstance()
        self.assertIsInstance(clone, OptimalHubSitingAlgorithm)

    def test_calculate_service_area_algorithm_metadata(self):
        alg = CalculateServiceAreaAlgorithm()
        self.assertEqual(alg.name(), "calculateservicearea")
        self.assertEqual(alg.groupId(), "logistics")
        self.assertIn("Service Area from Network", alg.displayName())
        clone = alg.createInstance()
        self.assertIsInstance(clone, CalculateServiceAreaAlgorithm)

    def test_provider_load_algorithms(self):
        provider = CartogenProcessingProvider()
        # Mock addAlgorithm if running outside real QGIS
        if not QGIS_PROCESSING_AVAILABLE:
            provider.addAlgorithm = MagicMock()
        provider.loadAlgorithms()
        self.assertEqual(len(provider._algs), 2)
        alg_names = {a.name() for a in provider._algs}
        self.assertIn("optimalhubsiting", alg_names)
        self.assertIn("calculateservicearea", alg_names)


if __name__ == "__main__":
    unittest.main()


class TestProviderPureHelpers(unittest.TestCase):
    """#156 / #157 (audit F20, F21): the parts of the native algorithms that do not need QGIS to check."""

    def test_pair_limit(self):
        from cartogen_ai.processing.provider import MAX_DISTANCE_PAIRS, pair_limit_error
        self.assertIsNone(pair_limit_error(1000, 1000))
        self.assertIsNone(pair_limit_error(1, MAX_DISTANCE_PAIRS))
        message = pair_limit_error(5000, 6000)
        self.assertIn("30,000,000", message)
        self.assertIn("Filter", message)

    def test_the_fastest_cost_is_converted_from_seconds_to_hours(self):
        from cartogen_ai.processing.provider import child_travel_cost
        self.assertEqual(child_travel_cost(0, 1000), 1000.0)          # shortest: metres, unchanged
        self.assertEqual(child_travel_cost(1, 3600), 1.0)             # fastest: 3,600 s is one hour for the child algorithm
        self.assertAlmostEqual(child_travel_cost(1, 900), 0.25)
