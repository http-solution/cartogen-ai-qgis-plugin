"""PLAN-014 phase 2 page sizes, no QGIS needed: the size names and the scale factors."""
import unittest

from cartogen_ai.core.agent.tools.layout_page_scale import PAGE_SIZE_KEYS, page_dimensions, scale_factor, validate_page_size


class TestPageSizeRules(unittest.TestCase):
    def test_only_the_a_series_the_owner_chose_is_accepted(self):
        self.assertEqual(PAGE_SIZE_KEYS, ("a4", "a3", "a2", "a1"))
        for text, key in (("A3", "a3"), (" a 2 ", "a2"), ("A1", "a1"), ("", "a4"), (None, "a4")):
            self.assertEqual(validate_page_size(text), (key, None), text)
        for refused in ("A5", "letter", "tabloid", "A0", "poster"):
            key, message = validate_page_size(refused)
            self.assertIsNone(key)
            self.assertIn("A4, A3, A2, A1", message)

    def test_dimensions_follow_the_orientation(self):
        self.assertEqual(page_dimensions("a4", "landscape"), (297, 210))
        self.assertEqual(page_dimensions("a3", "Portrait"), (297, 420))
        self.assertEqual(page_dimensions("a1", "landscape"), (841, 594))

    def test_a4_is_exactly_one_and_the_others_double_per_step(self):
        for orientation in ("landscape", "portrait"):
            self.assertEqual(scale_factor("a4", orientation), 1.0)
            self.assertAlmostEqual(scale_factor("a3", orientation), 2 ** 0.5, delta=0.001)
            self.assertAlmostEqual(scale_factor("a2", orientation), 2.0, delta=0.005)
            self.assertAlmostEqual(scale_factor("a1", orientation), 2 * 2 ** 0.5, delta=0.01)

    def test_the_factor_never_lets_an_a4_item_stick_out_of_the_bigger_page(self):
        for size in ("a3", "a2", "a1"):
            for orientation in ("landscape", "portrait"):
                k = scale_factor(size, orientation)
                base_w, base_h = page_dimensions("a4", orientation)
                w, h = page_dimensions(size, orientation)
                self.assertLessEqual(base_w * k, w + 1e-9)
                self.assertLessEqual(base_h * k, h + 1e-9)


if __name__ == "__main__":
    unittest.main()
