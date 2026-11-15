"""The 385 plain-language hand-test prompts (tools/plain_prompts_*.py) and how well the offline pieces handle them.

The prompts describe a humanitarian task and never name the algorithm. This test keeps three promises: every algorithm of the hand-test sheet has
a prompt and none leaks its name or id; the topic index finds the algorithm among the first 15 search results for most of them; and the router
offers the Processing tools for nearly all. The thresholds are a ratchet set just below the measured values on 2026-10-17 (89 percent found,
99 percent offered). Those prompts were used to improve the index, so the numbers flatter it: on 40 fresh requests written afterwards the
algorithm was among the first 15 results for 24 (60 percent). Which algorithm a real model then chooses is not tested here."""
import csv
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

import plain_prompts_grass  # noqa: E402
import plain_prompts_raster  # noqa: E402
import plain_prompts_vector  # noqa: E402

from cartogen_ai.core.agent.tools import TOOLS_SCHEMA  # noqa: E402
from cartogen_ai.core.agent.tools.processing_allowlist_tools import search_allowed_algorithms  # noqa: E402
from cartogen_ai.core.services.tool_router import ToolRouter  # noqa: E402

PROMPTS = {**plain_prompts_vector.PROMPTS, **plain_prompts_raster.PROMPTS, **plain_prompts_grass.PROMPTS}
GENERIC = {"find_processing_algorithm", "run_allowlisted_processing_algorithm"}


def _sheet_rows():
    with open(REPO / "docs/HAND_TEST_rc44_algorithms.csv", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


class PlainPromptTests(unittest.TestCase):
    def test_every_algorithm_of_the_sheet_has_exactly_one_prompt(self):
        self.assertEqual(set(PROMPTS), {row["algorithm_id"] for row in _sheet_rows()})

    def test_no_prompt_contains_the_algorithms_id_or_display_name(self):
        for row in _sheet_rows():
            prompt = PROMPTS[row["algorithm_id"]].lower()
            short = row["algorithm_id"].split(":", 1)[1].lower()
            self.assertNotIn(row["algorithm_id"].lower(), prompt)
            if len(short) > 6:
                self.assertNotIn(short, prompt, row["algorithm_id"])
            name = row["name"].lower()
            if len(name) > 8 and not name.startswith(("i.", "r.", "v.")):
                self.assertNotIn(name, prompt, row["algorithm_id"])

    def test_the_search_finds_the_algorithm_for_most_prompts(self):
        found = sum(alg_id in {i for i, _n in search_allowed_algorithms(prompt)} for alg_id, prompt in PROMPTS.items())
        self.assertGreaterEqual(found, 0.85 * len(PROMPTS), f"only {found} of {len(PROMPTS)}")

    def test_the_router_offers_the_processing_tools_for_nearly_all_prompts(self):
        router = ToolRouter(TOOLS_SCHEMA)
        offered = sum(bool({t["function"]["name"] for t in router.filter_relevant_tools(p)} & GENERIC) for p in PROMPTS.values())
        self.assertGreaterEqual(offered, 0.97 * len(PROMPTS), f"only {offered} of {len(PROMPTS)}")

    def test_the_csv_matches_the_prompts(self):
        with open(REPO / "docs/HAND_TEST_rc46_algorithms_plain.csv", encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual({r["algorithm_id"]: r["plain_prompt"] for r in rows}, PROMPTS,
                         "rebuild: python tools/build_plain_prompt_csv.py")


if __name__ == "__main__":
    unittest.main()
