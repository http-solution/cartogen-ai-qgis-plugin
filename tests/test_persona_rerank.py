"""PLAN-023 R1-4: the persona re-rank. Offline, no QGIS. Part 1 checks the pure selection on hand-made scores (known answers); part 2 replays every routing request the project keeps, with every persona,
against the real router and tool list."""
import json
import unittest
from pathlib import Path

from cartogen_ai.core import personas as pp
from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
from cartogen_ai.core.services import persona_rerank as pr
from cartogen_ai.core.services.tool_router import ToolRouter


def tool(name):
    return {"function": {"name": name}}


def scored(*pairs):
    return [(s, tool(n)) for n, s in pairs]


def names(tools):
    return [t["function"]["name"] for t in tools]


class TestBonuses(unittest.TestCase):
    def test_general_unknown_and_missing_personas_boost_nothing(self):
        for persona in ("general", "nonsense", "", None):
            self.assertEqual(pr.build_bonuses(persona, None, "anything"), {}, persona)

    def test_primary_gets_the_full_bonus_and_secondary_half_and_the_larger_wins(self):
        out = pr.build_bonuses("engineering", "logistics", "x")
        self.assertEqual(out["delineate_watershed"], 3.0)
        self.assertEqual(out["optimal_hub_siting"], 1.5)
        both = pr.build_bonuses("public_safety", "public_health", "x")
        self.assertEqual(both["hotspot_analysis"], 3.0)                     # in both lists: the full one

    def test_an_alias_phrase_in_the_request_counts_double(self):
        quiet = pr.build_bonuses("engineering", None, "make a map")
        loud = pr.build_bonuses("engineering", None, "delineate the drainage basin for the culvert")
        self.assertEqual(quiet["calculate_rational_watershed_peak_flow"], 3.0)
        self.assertEqual(loud["delineate_watershed"], 6.0)
        self.assertEqual(pr.build_bonuses(None, "engineering", "the drainage basin")["delineate_watershed"], 3.0)


class TestSelect(unittest.TestCase):
    BASE = scored(("a", 30), ("b", 20), ("c", 12), ("d", 11), ("e", 10), ("f", 9), ("g", 8), ("h", 7))

    def test_no_bonuses_is_the_old_slice(self):
        self.assertEqual(names(pr.select_tools(self.BASE, 4, 1, {})), ["a", "b", "c", "d"])

    def test_a_boosted_tool_just_below_the_cut_enters_and_the_last_ordinary_one_leaves(self):
        out = pr.select_tools(self.BASE, 4, 1, {"e": 3.0})                  # e: 10 + 3 = 13 beats c (12) and d (11)
        self.assertEqual(names(out), ["a", "b", "e", "c"])
        self.assertNotIn("d", names(out))

    def test_a_tool_with_no_relevance_is_never_boosted_in(self):
        base = scored(("a", 30), ("b", 20), ("c", 12), ("z", 0))
        self.assertEqual(names(pr.select_tools(base, 3, 1, {"z": 50.0})), ["a", "b", "c"])

    def test_at_most_five_enter_and_the_best_five_are_the_ones(self):
        base = scored(*[(f"o{i}", 100 - i) for i in range(10)], *[(f"p{i}", 50 - i) for i in range(8)])
        bonus = {f"p{i}": 100.0 + (8 - i) for i in range(8)}                # eight persona tools would all outrank every ordinary tool
        out = names(pr.select_tools(base, 10, 1, bonus))
        entered = [n for n in out if n.startswith("p")]
        self.assertEqual(len(entered), 5)
        self.assertEqual(sorted(entered), ["p0", "p1", "p2", "p3", "p4"])    # the best-boosted five
        self.assertEqual(len(out), 10)
        displaced = [f"o{i}" for i in range(10) if f"o{i}" not in out]
        self.assertEqual(displaced, ["o5", "o6", "o7", "o8", "o9"])          # only the five lowest ordinary tools
        for i in range(5):
            self.assertIn(f"o{i}", out)

    def test_always_included_tools_score_a_thousand_and_are_never_displaced(self):
        base = scored(("core", 1000), ("a", 30), ("b", 20), ("x", 10))
        out = pr.select_tools(base, 3, 1, {"x": 100.0})
        self.assertIn("core", names(out))

    def test_the_floor_still_applies_to_every_selected_tool(self):
        base = scored(("a", 30), ("b", 20), ("c", 3), ("d", 2))
        self.assertEqual(names(pr.select_tools(base, 4, 10, {"d": 3.0})), ["a", "b"])
        self.assertEqual(names(pr.select_tools(base, 4, 10, {})), ["a", "b"])

    def test_the_selection_never_has_more_tools_than_the_ordinary_one(self):
        out = pr.select_tools(self.BASE, 4, 1, {"e": 3.0, "f": 3.0, "g": 3.0})
        self.assertLessEqual(len(out), 4)


def _prompts():
    from tests.test_tool_router_basics import GOLDEN, GOLDEN_LONG
    rows = json.loads((Path(__file__).resolve().parent / "fixtures" / "routing_requests.json").read_text(encoding="utf-8"))
    out = [(r["prompt"], r["tools"]) for r in rows]
    out += [(p, list(t)) for p, t in GOLDEN.items()]
    out += [(p, list(t)) for p, t in GOLDEN_LONG.items()]
    return out


class TestReplayWithEveryPersona(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.router = ToolRouter(TOOLS_SCHEMA)
        cls.prompts = _prompts()

    def offered(self, prompt, primary=None, secondary=None):
        personas = (primary, secondary) if primary else None
        return {t["function"]["name"] for t in self.router.filter_relevant_tools(prompt, personas=personas)}

    def tied_at_the_cut(self, prompt):
        """Names of the tools whose score equals the lowest kept score. Which of those the router keeps is already arbitrary (it shuffles ties), so a persona may legitimately swap one of them."""
        seen = {}
        real = pr.select_tools

        def spy(scored, top_k, floor, bonuses, **kw):
            seen["scored"], seen["top_k"], seen["floor"] = scored, top_k, floor
            return real(scored, top_k, floor, bonuses, **kw)
        pr.select_tools = spy
        try:
            self.router.filter_relevant_tools(prompt)
        finally:
            pr.select_tools = real
        if "scored" not in seen:
            return set()
        kept = [(s, t) for s, t in seen["scored"][:seen["top_k"]] if s >= seen["floor"]]
        if not kept:
            return set()
        cut = kept[-1][0]
        return {t["function"]["name"] for s, t in seen["scored"] if s == cut}

    def test_the_generalist_gets_exactly_what_it_got_before(self):
        for prompt, _ in self.prompts:
            before = names(self.router.filter_relevant_tools(prompt))
            after = names(self.router.filter_relevant_tools(prompt, personas=("general", "")))
            self.assertEqual(after, before, prompt)

    def test_each_persona_changes_at_most_five_tools_and_never_removes_a_required_one(self):
        self.assertGreater(len(self.prompts), 180)
        for persona in pp.ids():
            for prompt, needed in self.prompts:
                base = self.offered(prompt)
                with_persona = self.offered(prompt, persona, None)
                self.assertLessEqual(len(with_persona - base), 5, f"{persona}: {prompt}")
                self.assertLessEqual(len(base - with_persona), 5, f"{persona}: {prompt}")
                for need in needed:
                    options = set(need) if isinstance(need, (list, tuple)) else {need}
                    if options & base and not options & with_persona:
                        self.assertTrue(options & base <= self.tied_at_the_cut(prompt), f"{persona} displaced a required tool that was not tied at the cut for: {prompt}")

    def test_a_secondary_persona_obeys_the_same_cap(self):
        for prompt, needed in self.prompts[:80]:
            base = self.offered(prompt)
            both = self.offered(prompt, "public_health", "logistics")
            self.assertLessEqual(len(both - base), 5, prompt)
            for need in needed:
                options = set(need) if isinstance(need, (list, tuple)) else {need}
                if options & base and not options & both:
                    self.assertTrue(options & base <= self.tied_at_the_cut(prompt), prompt)

    def test_the_persona_actually_helps_somewhere(self):
        # engineering with a request in its own words offers a tool it would not offer for the generalist (or already offers it): never fewer
        prompt = "work out the peak flow and the drainage basin at this culvert"
        self.assertTrue({"delineate_watershed", "calculate_rational_watershed_peak_flow"} <= self.offered(prompt, "engineering"))


if __name__ == "__main__":
    unittest.main()
