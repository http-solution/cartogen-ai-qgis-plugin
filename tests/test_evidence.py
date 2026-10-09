# -*- coding: utf-8 -*-
"""Evidence folder: files written, redaction, output copies with hashes, size limit, and the agent hook (off by default, on via setting)."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import cartogen_ai.core.agent.agent_orchestrator as agent_mod
from cartogen_ai.core.agent import evidence as ev
from tests.test_agent_runner import _make_bare_agent
from tests.test_run_steps import _Scripted, _call, _tools


class TestRecorder(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ev_")
        self.rec = ev.EvidenceRecorder(os.path.join(self.dir, "t1"), "buffer the roads token=abc123")

    def test_a_call_with_an_output_file_is_copied_and_hashed(self):
        out = os.path.join(self.dir, "report.csv")
        open(out, "w").write("a,b\n1,2\n")
        self.rec.record_call("export_layer", {"layer_name": "roads", "api_key": "sekret"}, {"success": True, "path": out}, 12, ["roads_x"])
        self.rec.finish("Done.", usage_line="3 calls", screenshot_fn=lambda p: open(p, "wb").write(b"png") and True)
        folder = self.rec.folder
        manifest = json.load(open(os.path.join(folder, "manifest.json")))
        self.assertEqual(manifest["files"][0]["sha256"], ev.sha256_of(out))
        self.assertTrue(os.path.isfile(os.path.join(folder, manifest["files"][0]["copy"])))
        self.assertEqual(manifest["screenshot"]["file"], "screenshot.png")
        line = json.loads(open(os.path.join(folder, "steps.jsonl")).read().splitlines()[0])
        self.assertEqual((line["tool"], line["ok"], line["new_layers"]), ("export_layer", True, ["roads_x"]))
        text = open(os.path.join(folder, "steps.jsonl")).read() + open(os.path.join(folder, "summary.md")).read()
        self.assertNotIn("sekret", text)
        self.assertNotIn("abc123", text)
        self.assertIn("| 1 | `export_layer` | yes |", open(os.path.join(folder, "summary.md")).read())

    def test_a_failed_call_is_marked_and_a_missing_screenshot_is_not_an_error(self):
        self.rec.record_call("clip_layer", {}, {"error": "boom"}, 5)
        self.rec.finish("It failed.", screenshot_fn=lambda p: False)
        self.assertIn("| NO |", open(os.path.join(self.rec.folder, "summary.md")).read())
        self.assertNotIn("screenshot", json.load(open(os.path.join(self.rec.folder, "manifest.json"))))

    def test_oversized_outputs_are_hashed_but_not_copied(self):
        big = os.path.join(self.dir, "big.bin")
        open(big, "wb").write(b"x" * 10)
        with patch.object(ev, "MAX_COPY_BYTES", 5):
            self.rec.record_call("export_layer", {}, {"path": big}, 1)
            self.rec.finish("")
        entry = json.load(open(os.path.join(self.rec.folder, "manifest.json")))["files"][0]
        self.assertFalse(entry["copied"])
        self.assertEqual(entry["sha256"], ev.sha256_of(big))

    def test_the_folder_is_relative_so_it_lands_in_the_project(self):
        self.assertFalse(os.path.isabs(ev.relative_folder("t3")))
        self.assertTrue(ev.relative_folder("t3").startswith("cartogen_evidence"))


class _Settings:
    values = {}

    def value(self, key, default=None, *a, **k):
        return self.values.get(key, default)


class TestAgentHook(unittest.TestCase):
    def run_turn(self, enabled):
        base = tempfile.mkdtemp(prefix="ev_home_")
        _Settings.values = {"cartogen_ai/evidence_enabled": enabled}
        chain = [{"tool": "buffer_layer", "arguments": {"layer_name": "roads", "distance": 100}},
                 {"tool": "clip_layer", "arguments": {"input_layer": "$prev.layer_name", "overlay_layer": "z"}}]
        client = _Scripted([{"role": "assistant", "content": None, "tool_calls": [_call(1, "run_steps", {"steps": chain})]},
                            {"role": "assistant", "content": "done"}])
        agent = _make_bare_agent(client)
        with patch.object(agent_mod, "QgsSettings", _Settings), \
             patch("cartogen_ai.core.agent.tools._paths._project_home", lambda: base), \
             patch.object(agent_mod.CartogenAi, "_apply_auto_model_selection", lambda self, q: None), \
             patch.object(agent_mod.CartogenAi, "_execute_tool", lambda self, n, a: {"success": True, "layer_name": n + "_out"}), \
             patch("cartogen_ai.core.agent.agent_orchestrator.build_system_prompt", return_value="sys"), \
             patch("cartogen_ai.core.agent.agent_orchestrator.TOOLS_SCHEMA", _tools("buffer_layer", "clip_layer", "run_steps")), \
             patch("cartogen_ai.core.agent.agent_orchestrator.time.sleep"):
            agent.run("buffer then clip")
        return base

    def test_off_by_default_writes_nothing(self):
        base = self.run_turn(False)
        self.assertFalse(os.path.exists(os.path.join(base, "cartogen_evidence")))

    def test_on_records_each_inner_step_and_the_reply(self):
        base = self.run_turn(True)
        root = os.path.join(base, "cartogen_evidence")
        folder = os.path.join(root, os.listdir(root)[0])
        steps = [json.loads(line) for line in open(os.path.join(folder, "steps.jsonl"))]
        self.assertEqual([s["tool"] for s in steps], ["buffer_layer", "clip_layer"])
        self.assertEqual(steps[1]["arguments"]["input_layer"], "buffer_layer_out")      # the REAL resolved argument, not the reference
        self.assertIn("done", open(os.path.join(folder, "summary.md")).read())


if __name__ == "__main__":
    unittest.main()
