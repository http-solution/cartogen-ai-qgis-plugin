"""DEF-6 (master list): a nationwide task grid above the limit was refused with only "Use a larger cell_size_m". The refusal now also says WHICH size
would work and about how many tasks that gives, and what else can be done (a part of the area at a time). It only suggests: the cell size is an
operational choice (what a field team can cover), so nothing is changed or run automatically. Pure functions here; the live behaviour is in
tests/test_task_grid_tools_live.py."""
import math
import unittest

from cartogen_ai.core.agent.tools import task_grid_tools as tg


class TestSizeText(unittest.TestCase):
    def test_metres_below_a_kilometre_and_kilometres_above(self):
        self.assertEqual(tg.size_text(500), "500 m")
        self.assertEqual(tg.size_text(1000), "1 km")
        self.assertEqual(tg.size_text(2500), "2.5 km")
        self.assertEqual(tg.size_text(15000), "15 km")


class TestSuggestCellSize(unittest.TestCase):
    def test_it_picks_the_smallest_round_size_that_fits_the_limit(self):
        # Yemen-like box: about 1,400 km by 600 km
        size, cells = tg.suggest_cell_size(1_400_000, 600_000, 5000)
        self.assertLessEqual(cells, tg.MAX_TASKS)
        smaller = [s for s in tg.size_ladder() if 5000 <= s < size]
        for s in smaller:
            self.assertGreater(tg.estimated_cells(1_400_000, 600_000, s), tg.MAX_TASKS, s)

    def test_the_count_it_reports_is_the_real_estimate_for_that_size(self):
        size, cells = tg.suggest_cell_size(300_000, 200_000, 1000)
        self.assertEqual(cells, tg.estimated_cells(300_000, 200_000, size))

    def test_it_never_suggests_a_smaller_size_than_the_one_asked_for(self):
        size, _ = tg.suggest_cell_size(50_000, 40_000, 4000)
        self.assertGreaterEqual(size, 4000)

    def test_an_area_that_already_fits_gets_the_size_asked_for(self):
        size, cells = tg.suggest_cell_size(40_000, 30_000, 2000)
        self.assertEqual(size, 2000)
        self.assertLessEqual(cells, tg.MAX_TASKS)

    def test_sizes_are_round_so_they_are_easy_to_say_and_remember(self):
        for width in (777_000, 1_234_567, 90_000):
            size, _ = tg.suggest_cell_size(width, width / 2, 1000)
            self.assertIn(size, tg.size_ladder())

    def test_an_area_too_big_for_any_size_returns_none_rather_than_a_nonsense_size(self):
        self.assertEqual(tg.suggest_cell_size(1e12, 1e12, 1000), (None, None))


class TestLadder(unittest.TestCase):
    def test_it_is_increasing_starts_at_the_minimum_and_has_the_round_steps(self):
        ladder = tg.size_ladder()
        self.assertEqual(ladder, sorted(set(ladder)))
        self.assertEqual(ladder[0], tg.MIN_CELL_SIZE_M)
        for wanted in (100, 150, 200, 250, 300, 400, 500, 600, 800, 1000, 1500, 2000, 2500, 5000, 10000, 15000, 20000, 50000):
            self.assertIn(wanted, ladder)


class TestRefusalText(unittest.TestCase):
    def test_the_bounding_box_refusal_names_the_size_and_the_other_way_out(self):
        text = tg.too_many_cells_message(5000, 4_000_000, 1_400_000, 600_000)
        self.assertIn("larger cell_size_m", text)
        size, cells = tg.suggest_cell_size(1_400_000, 600_000, 5000)
        self.assertIn(tg.size_text(size), text)
        self.assertIn(f"{cells:,}", text)
        self.assertIn("aoi_where", text)

    def test_the_wording_says_it_is_a_suggestion_and_nothing_was_run(self):
        text = tg.too_many_cells_message(5000, 4_000_000, 1_400_000, 600_000)
        self.assertIn("No grid was made", text)

    def test_the_after_clipping_refusal_scales_from_the_real_count(self):
        # 9,000 tasks at 2 km: tasks go with 1/size squared, so the size must grow by at least sqrt(9000/5000)
        size, count = tg.suggest_size_from_count(2000, 9000)
        self.assertGreaterEqual(size, 2000 * math.sqrt(9000 / tg.MAX_TASKS))
        self.assertIn(size, tg.size_ladder())
        self.assertLessEqual(count, tg.MAX_TASKS * 1.15)       # about: edge cells do not scale exactly

    def test_when_nothing_is_suggestible_the_message_still_gives_the_old_advice(self):
        text = tg.too_many_cells_message(1000, 10**12, 1e12, 1e12)
        self.assertIn("larger cell_size_m", text)
        self.assertNotIn("None", text)

    def test_the_after_clipping_result_names_the_size_the_count_and_says_nothing_was_made(self):
        found = tg.too_many_tasks_result(2000, 9000)
        self.assertIn("9,000", found["error"])
        self.assertIn("No grid was made", found["error"])
        self.assertIn(tg.size_text(found["suggested_cell_size_m"]), found["error"])
        self.assertGreater(found["suggested_cell_size_m"], 2000)
        self.assertNotIn("suggested_cell_size_m", tg.too_many_tasks_result(10_000_000, 10**15))

    def test_the_result_carries_the_numbers_for_the_assistant_to_offer(self):
        found = tg.refusal_result(5000, 4_000_000, 1_400_000, 600_000)
        self.assertIn("error", found)
        self.assertGreater(found["suggested_cell_size_m"], 5000)
        self.assertLessEqual(found["suggested_cells"], tg.MAX_TASKS)


if __name__ == "__main__":
    unittest.main()
