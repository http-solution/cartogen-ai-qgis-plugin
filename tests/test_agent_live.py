# -*- coding: utf-8 -*-
"""Headless functional test of the full agent execution pipeline against a REAL QGIS
process -- real CartogenAi() agent, real task_manager/memory_manager (bound via the same
bind_agent_context() production __init__ already calls), real TOOL_REGISTRY, real
QgsProject. Only the LLM network boundary (agent.client) is a scripted fake.

Every other check in this repo's test suite mocks _execute_tool/_execute_tool_dispatch
directly (see test_agent_runner.py) -- that proves the tool-calling LOOP is correct, but
never proves a tool call actually creates a real QGIS layer, or that task_manager's plan
(what tasks_tab_widget.py's Activity tab renders) actually gets populated. This module is
what checks that, the same gap test_chat_widget_live.py closes for the chat UI's own Qt
signal wiring.

Real live report, 2026-09-16: "the last test no layers created in the map and stepped no
activity recorded in the activity double check processing of full example make a test
script" -- a real Gemini run of "Health facilities beyond one hour's travel <coords>"
(after the router-alias fix made geocode_and_enrich/geocode_batch reachable again, see
test_tool_router.py's test_health_facilities_by_coordinates_finds_geocode_tools) produced
neither a layer nor any Activity-tab entries. TestFullExamplePipeline below scripts the
exact "well-behaved" tool sequence the task actually needs (get_layers -> create_plan ->
update_task -> add_point_layer -> update_task -> apply_categorized_style -> update_task)
and confirms: when the model DOES call these tools, a real layer appears in QgsProject with
the right feature count and a real categorized renderer, and task_manager's plan shows both
tasks DONE -- i.e. the execution/tracking pipeline itself is not broken. That narrows the
live report to the model's own tool choice for that specific run (still needs a real
console log to confirm which path it actually took), not this codebase's plumbing.

Requires real qgis.core + qgis.PyQt bindings, unlike the rest of this suite. Skips itself
entirely when those bindings are not importable. Run it from an OSGeo4W/QGIS Python (see
docs/RELEASE_SMOKE_TEST.md): `python -m unittest tests.test_agent_live -v`.
"""
import json
import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from qgis.core import QgsApplication, QgsProject
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False

_APP = None


def _boot_qgis():
    global _APP
    if _APP is None:
        # GUI mode True, not False (test_chat_widget_live.py's own _boot_qgis() uses False,
        # but that file never exercises real tool execution -- its fakes never touch
        # qgis.core at all) -- matches CLAUDE.md's own documented guidance ("QgsApplication
        # ([], True) -- GUI mode, not False") for reliably getting a fully working QGIS
        # environment in this sandbox.
        _APP = QgsApplication([], True)
        _APP.initQgis()
        # Confirmed live: without this, `import processing` inside vector_tools.py/
        # styling_tools.py's own QGIS_AVAILABLE try/except raised a bare ModuleNotFoundError
        # (reproduced directly, both as a plain script AND under unittest -- this is not a
        # unittest-specific quirk), leaving QGIS_AVAILABLE False in exactly those two modules
        # even though qgis.core itself imported fine -- every real tool call in this file's
        # test then failed with "QGIS not available" instead of actually running.
        # tests/__init__.py's bootstrap only puts src/ on sys.path; it has no reason to also
        # know about QGIS's OWN python/plugins directory (where the built-in `processing`
        # package lives, since it's a QGIS core plugin, not a pip package) -- nothing else in
        # this suite needs it, since this is the first test file to exercise real
        # processing-dependent tool code rather than mocking around it. Resolved dynamically
        # from the now-initialized QgsApplication rather than hardcoding one QGIS version's
        # install path, so this doesn't silently break on the next QGIS upgrade.
        plugins_dir = os.path.join(QgsApplication.pkgDataPath(), "python", "plugins")
        if os.path.isdir(plugins_dir) and plugins_dir not in sys.path:
            sys.path.insert(0, plugins_dir)
    return _APP


def _tool_call(call_id, name, arguments_obj):
    return {"id": call_id, "function": {"name": name, "arguments": json.dumps(arguments_obj)}}


class _ScriptedClient:
    """Stands in for the network call inside agent.run() -- a scripted list of response
    dicts, consumed in order, the same shape test_chat_widget_live.py's own _FakeClient
    uses. A call past the end of the script is itself a signal the loop went further than
    expected (returned as a harmless no-op response rather than raising, so a genuine
    over-run shows up as a failed assertion on the resulting state, not a crash)."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def complete(self, messages, tools=None, **kw):
        self.calls += 1
        if not self.script:
            return {"message": {"role": "assistant", "content": "(script exhausted)", "tool_calls": []}}
        return self.script.pop(0)


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core/qgis.PyQt bindings -- run from an OSGeo4W/QGIS Python")
class TestFullExamplePipeline(unittest.TestCase):
    """Each test gets a cleared QgsProject -- see setUp -- the same per-test isolation
    test_chat_widget_live.py's own class docstring explains the reasoning for."""

    @classmethod
    def setUpClass(cls):
        _boot_qgis()
        # Imported here, immediately after initQgis(), not lazily inside a test method --
        # confirmed live: importing cartogen_ai.core.agent.agent (which transitively imports
        # every agent/tools/*.py module, several of which do `import processing` inside their
        # own QGIS_AVAILABLE try/except -- see vector_tools.py/styling_tools.py) from inside a
        # test method left QGIS_AVAILABLE False in some of those modules even though the same
        # import sequence run as a plain top-level script right after initQgis() resolved True
        # every time. Matches this file's module-level import style to what actually worked,
        # rather than something unittest's own test-loading machinery does differently.
        import cartogen_ai.core.agent.agent as agent_mod
        cls.agent_mod = agent_mod

    def setUp(self):
        QgsProject.instance().clear()

    def _make_agent(self, script):
        agent = self.agent_mod.CartogenAi()  # real task_manager/memory_manager, bound for real
        agent.client = _ScriptedClient(script)
        return agent, self.agent_mod

    def test_health_facilities_task_creates_a_real_layer_and_records_activity(self):
        """The exact reported scenario: 'Health facilities beyond one hour's travel
        <coords>', with a well-behaved tool sequence (get_layers -> create_plan ->
        update_task -> add_point_layer -> update_task -> apply_categorized_style ->
        update_task). geocode_batch's own tool call is intentionally not in this script --
        a real Nominatim network call would make this test flaky/slow, and its
        reachability is separately verified in test_tool_router.py -- add_point_layer is
        fed realistic already-geocoded coordinates directly, exactly what a real
        geocode_batch result would feed into it. This test's job is the DOWNSTREAM half:
        does a real tool sequence actually create layers and record activity."""
        layer_name = "Health Facilities"
        script = [
            {"message": {"role": "assistant", "content": None, "tool_calls": [
                _tool_call("c1", "get_layers", {}),
            ]}},
            {"message": {"role": "assistant", "content": None, "tool_calls": [
                _tool_call("c2", "create_plan", {
                    "title": "Map Health Facilities Beyond One Hour Travel",
                    "task_descriptions": [
                        "Add health facilities to the canvas",
                        "Apply categorized styling to distinguish access",
                    ],
                }),
            ]}},
            {"message": {"role": "assistant", "content": None, "tool_calls": [
                _tool_call("c3", "update_task", {"task_id": "1", "status": "IN_PROGRESS", "rationale": "Adding facilities."}),
            ]}},
            {"message": {"role": "assistant", "content": None, "tool_calls": [
                _tool_call("c4", "add_point_layer", {
                    "layer_name": layer_name,
                    "points": [
                        {"name": "Al-Bashir Hospital (Amman)", "lat": 31.9392942, "lon": 35.9406933, "category": "Within 1 Hour"},
                        {"name": "Princess Basma Hospital (Irbid)", "lat": 32.529803, "lon": 35.8292668, "category": "Beyond 1 Hour"},
                        {"name": "Karak Governmental Hospital", "lat": 31.1817, "lon": 35.7048, "category": "Beyond 1 Hour"},
                    ],
                }),
            ]}},
            {"message": {"role": "assistant", "content": None, "tool_calls": [
                _tool_call("c5", "update_task", {"task_id": "1", "status": "DONE", "result": "3 facilities added."}),
            ]}},
            {"message": {"role": "assistant", "content": None, "tool_calls": [
                _tool_call("c6", "apply_categorized_style", {"layer_name": layer_name, "field": "category"}),
            ]}},
            {"message": {"role": "assistant", "content": None, "tool_calls": [
                _tool_call("c7", "update_task", {"task_id": "2", "status": "DONE", "result": "Styled by access category."}),
            ]}},
            {"message": {"role": "assistant", "content": "Added 3 health facilities, styled by 1-hour access category.", "tool_calls": []}},
        ]
        agent, agent_mod = self._make_agent(script)

        with patch("cartogen_ai.core.agent.agent.build_system_prompt", return_value="sys"), \
             patch.object(agent_mod.CartogenAi, "_apply_auto_model_selection", lambda self, q: None):
            final_text = agent.run("Health facilities beyond one hour's travel 4178029,3463954")

        self.assertIn("3 health facilities", final_text)

        # 1. A real QGIS layer, not just a tool returning {"success": True}.
        layers = QgsProject.instance().mapLayersByName(layer_name)
        self.assertEqual(len(layers), 1, "expected exactly one 'Health Facilities' layer in the project")
        self.assertEqual(layers[0].featureCount(), 3)
        self.assertEqual(layers[0].renderer().type(), "categorizedSymbol",
                          "apply_categorized_style must have actually applied a categorized renderer")

        # 2. task_manager's plan -- exactly what tasks_tab_widget.py's Activity tab renders
        # (_render_plan/_on_live_plan_updated read task_manager.get_plan() the same way).
        plan = agent.task_manager.get_plan()
        tasks = plan.get("tasks", [])
        self.assertEqual(len(tasks), 2, "expected both plan tasks from create_plan()")
        statuses = [t.get("status") for t in tasks]
        self.assertEqual(statuses, ["DONE", "DONE"],
                          "both tasks must be recorded DONE -- an empty/stale Activity tab "
                          "means this list is empty or still TODO, not that nothing rendered")


if __name__ == "__main__":
    unittest.main()
