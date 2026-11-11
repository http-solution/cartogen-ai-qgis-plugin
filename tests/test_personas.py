"""PLAN-023 R1-1 (and the text check of R1-9): the persona pack. Offline, no QGIS.

The 15 files in src/cartogen_ai/core/personas/ say, per kind of user, what the plugin can do today (CI-checked), what is not built (with the release that will deliver it) and what is out of scope or
declined, and which tools the router may rank higher. These tests keep them true: every tool named exists in the registry, the ids equal the refinement persona list, no file claims more than the evidence
allows, and the checker itself catches each kind of fault (shown on synthetic personas, so a checker that accepts everything cannot pass)."""
import copy
import unittest

from cartogen_ai.core import personas as pp
from cartogen_ai.core.agent.tools.registry import TOOL_REGISTRY
from cartogen_ai.core.services.prompt_refiner import PROFILE_GUIDANCE, PROFILE_LABELS


def _good():
    return {"id": "x", "number": 3, "label": "X", "aliases": [], "summary": "s", "guidance": "g", "workflows": [{"id": "x.a", "title": "A", "tools": ["get_layers"]}], "tool_priority": ["get_layers"],
            "tool_aliases": {}, "task_ids": [], "data_sources": [], "style_profile": "x", "layout_templates": [],
            "readiness": [{"capability": "c", "state": "CI-checked", "tool": "get_layers"}], "guardrails": ["Say what was assumed."]}


class TestSchema(unittest.TestCase):
    def test_the_fifteen_ids_equal_the_refinement_persona_list_in_order(self):
        self.assertEqual(pp.ids(), list(PROFILE_LABELS))
        self.assertEqual([pp.get(i)["number"] for i in pp.ids()], list(range(1, 16)))
        for pid, label in PROFILE_LABELS.items():
            self.assertEqual(pp.get(pid)["label"], label, pid)

    def test_the_guidance_text_has_not_drifted_from_the_prompt_refiner(self):
        for pid, text in PROFILE_GUIDANCE.items():
            self.assertEqual(pp.get(pid)["guidance"], text, pid)

    def test_every_persona_passes_the_checker_against_the_real_registry(self):
        problems = []
        for persona in pp.load_all().values():
            problems += pp.validate(persona, tool_names=set(TOOL_REGISTRY), task_ids=set())
        self.assertEqual(problems, [], "\n" + "\n".join(problems))

    def test_a_persona_has_only_the_known_fields_and_no_tier_or_hiding_logic(self):
        for pid, persona in pp.load_all().items():
            self.assertEqual(set(persona), set(pp.REQUIRED), pid)

    def test_no_file_claims_a_live_run_it_cannot_show(self):
        for pid, persona in pp.load_all().items():
            for item in persona["readiness"]:
                self.assertNotEqual(item["state"], "built", f"{pid}: '{item['capability']}' is marked built; use CI-checked until docs/LIVE_RESULTS.json records the feature working")

    def test_every_persona_has_at_least_one_checked_capability_or_says_why_not(self):
        for pid, persona in pp.load_all().items():
            states = {r["state"] for r in persona["readiness"]}
            self.assertTrue({"CI-checked", "built"} & states, pid)


class TestTheCheckerCatchesEachFault(unittest.TestCase):
    def problems(self, change, **kw):
        persona = _good()
        change(persona)
        return pp.validate(persona, tool_names=set(TOOL_REGISTRY), task_ids={"1.01"}, working_features=kw.get("working", set()))

    def test_a_good_persona_has_no_problems(self):
        self.assertEqual(pp.validate(_good(), tool_names=set(TOOL_REGISTRY), task_ids=set()), [])

    def test_each_fault_is_reported_with_the_persona_and_the_cause(self):
        cases = [
            (lambda p: p.pop("summary"), "missing field 'summary'"),
            (lambda p: p.update(number=16), "from 1 to 15"),
            (lambda p: p.update(tool_priority=[f"t{i}" for i in range(13)]), "at most 12"),
            (lambda p: p.update(tool_priority=["get_layers", "get_layers"]), "at most 12 different"),
            (lambda p: p.update(tool_priority=["no_such_tool"]), "'no_such_tool' is not a registered tool"),
            (lambda p: p["workflows"][0].update(tools=["also_missing"]), "'also_missing' is not a registered tool"),
            (lambda p: p.update(task_ids=["9.99"]), "task id '9.99'"),
            (lambda p: p["readiness"][0].update(state="great"), "state 'great'"),
            (lambda p: p["readiness"][0].pop("tool"), "names no tool"),
            (lambda p: p["readiness"].append({"capability": "n", "state": "not built"}), "no release"),
            (lambda p: p["readiness"].append({"capability": "o", "state": "out of scope"}), "gives no reason"),
            (lambda p: p["readiness"].append({"capability": "b", "state": "built", "tool": "get_layers", "feature": "nope"}), "no live run saw feature"),
            (lambda p: p.update(guardrails=[]), "guardrails"),
            (lambda p: p["workflows"].append({"id": "", "title": "", "tools": []}), "workflow needs"),
        ]
        for change, word in cases:
            found = self.problems(change)
            self.assertTrue(any(word in f and f.startswith("x:") for f in found), (word, found))

    def test_built_is_accepted_only_with_a_working_live_feature(self):
        def make_built(p):
            p["readiness"].append({"capability": "b", "state": "built", "tool": "get_layers", "feature": "feat"})
        self.assertEqual(self.problems(make_built, working={"feat"}), [])
        self.assertTrue(self.problems(make_built, working=set()))

    def test_the_checker_does_not_mutate_its_input(self):
        persona = _good()
        before = copy.deepcopy(persona)
        pp.validate(persona, tool_names=set(TOOL_REGISTRY))
        self.assertEqual(persona, before)


class TestPersonaFifteen(unittest.TestCase):
    """R1-9: the defence and intelligence profile is shown, and says plainly what is and is not available."""

    def test_the_readiness_text_is_the_agreed_sentence(self):
        persona = pp.get("defense_intel")
        text = " ".join(r.get("reason", "") for r in persona["readiness"])
        self.assertIn("Not built as written. Open-source conflict and access analysis is available under Humanitarian and Public Safety. Classified data must never be used with this plugin.", text)
        self.assertTrue(any("Classified" in g for g in persona["guardrails"]))


if __name__ == "__main__":
    unittest.main()
