import unittest

from cartogen_ai.core.agent.tools.raster_expression import validate_raster_expression as check

BANDS = {"dem": 1, "nir": 4, "red": 4, "land cover": 1}


class TestAccepted(unittest.TestCase):
    def test_documented_forms_pass_and_return_their_references(self):
        cases = {
            '"dem@1" > 100': [("dem", 1)],
            '("nir@4" - "red@3") / ("nir@4" + "red@3")': [("nir", 4), ("red", 3), ("nir", 4), ("red", 3)],
            '"dem@1" > 100 AND "land cover@1" = 2': [("dem", 1), ("land cover", 1)],
            'sqrt("dem@1") * 2.5e-1 + abs(-3)': [("dem", 1)],
            'min("nir@1", "red@2") <= max("nir@1", 10) or "dem@1" != 0': [("nir", 1), ("red", 2), ("nir", 1), ("dem", 1)],
        }
        for expression, refs in cases.items():
            result = check(expression, BANDS)
            self.assertTrue(result["ok"], (expression, result))
            self.assertEqual(result["refs"], refs)

    def test_without_a_layer_table_only_the_shape_is_checked(self):
        self.assertTrue(check('"anything@9" * 2')["ok"])


class TestRefused(unittest.TestCase):
    def assertRefused(self, expression, fragment, bands=BANDS):
        result = check(expression, bands)
        self.assertFalse(result["ok"], expression)
        self.assertIn(fragment, result["error"], expression)

    def test_code_and_unknown_words_are_refused(self):
        self.assertRefused('__import__("os")', "not allowed")
        self.assertRefused('"dem@1" + exec(1)', "not allowed")
        self.assertRefused('"dem@1"; 1', "';'")
        self.assertRefused('`ls`', "'`'")
        self.assertRefused('"dem@1" ** 2 + dem', "not allowed")
        self.assertRefused('numpy.where(1)', "not allowed")

    def test_a_function_name_without_a_call_is_refused(self):
        self.assertRefused('sqrt + "dem@1"', "not allowed")

    def test_reference_problems_name_the_layer(self):
        self.assertRefused('"nope@1" + 1', "no raster layer named 'nope'")
        self.assertRefused('"dem@2" + 1', "band 2 does not exist")
        self.assertRefused('"dem@0" + 1', "start at 1")
        self.assertRefused('"dem" + 1', "not a layer reference")
        self.assertRefused('"dem@1 + 1', "not closed")

    def test_structure_problems(self):
        self.assertRefused("", "empty")
        self.assertRefused("   ", "empty")
        self.assertRefused('("dem@1" + 1', "not closed")
        self.assertRefused('"dem@1" + 1)', "no matching")
        self.assertRefused("1 + 2", "names no raster")
        self.assertRefused('"dem@1" + ' + "1" * 2100, "longer than")

    def test_unknown_layer_lists_the_available_ones(self):
        self.assertEqual(check('"x@1"', BANDS)["available"], sorted(BANDS))


if __name__ == "__main__":
    unittest.main()
