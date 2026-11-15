"""PLAN-043: two sets of long, multi-step requests that measure whether the router offers a tool for every step.

Set 1 (routing_heldout_long.json, 41 requests) was written blind on 2026-11-01: 24 of the 41 were missing at least one needed tool. 32 of the
33 missing tools never scored above the long-request floor of 9 on ANY step, i.e. a vocabulary gap, not a shortage of slots; a per-step slot
allocation and an alphabetical-tie replacement (PLAN-043 options B and C) were built and changed nothing (24 of 41 both ways), so they were not
shipped. The vocabulary gaps were then patched, which is why set 1 is now "patched to fit" and allows 2 misses.

Set 2 (routing_blind_long_2.json, 20 requests) was written AFTER that patch and has not been used to patch anything: it is the honest measure.
10 of 20 miss a needed tool today and all 17 missing tools are vocabulary gaps. The pin below may only go DOWN; lower it when a change improves
it, and never fit the router to this file (write a third set instead)."""
import json
import unittest
from pathlib import Path

from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
from cartogen_ai.core.services.tool_router import ToolRouter

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REGISTERED = {t["function"]["name"] for t in TOOLS_SCHEMA}
SET1_MAX_MISSES = 2          # patched to fit; was 24 of 41
SET2_MAX_MISSES = 10         # blind; lower when a change improves it


def _flat(items):
    for item in items:
        if isinstance(item, list):
            yield from _flat(item)
        else:
            yield item


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _missing(rows):
    router = ToolRouter(TOOLS_SCHEMA)
    out = []
    for row in rows:
        offered = {t["function"]["name"] for t in router.filter_relevant_tools(row["prompt"])}
        gone = [n for n in row["tools"] if (not (set(_flat(n)) & offered) if isinstance(n, list) else n not in offered)]
        if gone:
            out.append((row["prompt"][:60], gone))
    return out


class TestHeldOutRoutingReplay(unittest.TestCase):
    def test_both_sets_are_long_requests_with_registered_tools(self):
        for name, floor in (("routing_heldout_long.json", 40), ("routing_blind_long_2.json", 20)):
            rows = _load(name)
            self.assertGreaterEqual(len(rows), floor, name)
            for row in rows:
                self.assertGreater(len(row["prompt"].split()), 17, row["prompt"][:60])   # multi-step; a few Arabic ones are under the 25-word long rule
                self.assertLessEqual(set(_flat(row["tools"])), REGISTERED, row["prompt"][:60])

    def test_set_1_stays_patched(self):
        misses = _missing(_load("routing_heldout_long.json"))
        self.assertLessEqual(len(misses), SET1_MAX_MISSES, misses)

    def test_set_2_blind_does_not_get_worse(self):
        misses = _missing(_load("routing_blind_long_2.json"))
        self.assertLessEqual(len(misses), SET2_MAX_MISSES, misses)

    def test_the_offered_list_is_deterministic(self):
        router = ToolRouter(TOOLS_SCHEMA)
        for row in _load("routing_blind_long_2.json")[:8]:
            first = [t["function"]["name"] for t in router.filter_relevant_tools(row["prompt"])]
            self.assertEqual(first, [t["function"]["name"] for t in router.filter_relevant_tools(row["prompt"])])


if __name__ == "__main__":
    unittest.main()
