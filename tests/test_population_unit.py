"""#160: a population density raster must not be summed as head-counts."""
import unittest

from cartogen_ai.core.agent.tools.raster_tools import population_unit_problem


class TestPopulationUnit(unittest.TestCase):
    def test_a_counts_raster_passes(self):
        for name in ("YEM_population_2020", "yem_ppp_2020", "pop"):
            self.assertIsNone(population_unit_problem(name, "people_per_cell"), name)

    def test_a_density_looking_name_is_refused_until_the_unit_is_set(self):
        for name in ("YEM_pd_2020", "pop_density", "people_per_km2", "population density 2020", "gpw_popden"):
            self.assertIn("DENSITY", population_unit_problem(name, "people_per_cell"), name)
            self.assertIsNone(population_unit_problem(name, "people_per_km2"), name)

    def test_an_unknown_unit_is_an_error(self):
        self.assertIn("raster_unit must be one of", population_unit_problem("x", "per_pixel"))


if __name__ == "__main__":
    unittest.main()
