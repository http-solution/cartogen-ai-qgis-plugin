"""PLAN-050, no QGIS needed: the tools and fixtures of the W rows of the hand test work against the real code, so a tester's first run is not their
first execution. The MCP probe runs against the real in-process server (a fake tool call stands in for QGIS); the workflow checker runs against the
shipped fixtures. What these cannot show: the probe against a server inside QGIS, and any dialog."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / "docs" / "hand_test_v2_inputs"


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


probe_module = load("mcp_probe")
checker = load("check_workflow_file")
validate_one, workflow_module = checker.validator()[1], checker.validator()[0]


def schema(name):
    return {"type": "function", "function": {"name": name, "description": name, "parameters": {"type": "object", "properties": {"layer_name": {"type": "string"}}}}}


class TestProbeAgainstTheRealServer(unittest.TestCase):
    def run_probe(self, **flags):
        from cartogen_ai.core.agent import mcp_server, tool_lists
        names = sorted(tool_lists.READ_TOOLS | tool_lists.WRITE_TOOLS | {"execute_pyqgis_script"})

        def fake(name, arguments):
            if name == "buffer_analysis":              # what run_allowed_tool returns when the person presses Deny (pinned by test_mcp_server)
                return {"status": "DENIED", "error": "The user did not approve this call in QGIS. Nothing was changed."}
            if arguments.get("layer_name") == "secret":
                return {"error": "This layer is SENSITIVE and is not available."}
            return {"success": True, "layer_name": arguments.get("layer_name"), "feature_count": 5}

        server = mcp_server.McpServer(lambda f, a: f(a), schemas=[schema(n) for n in names], call_tool=fake, approve=lambda n, t: False)
        server.start()
        self.addCleanup(server.stop)
        out = tempfile.mkdtemp()
        args = probe_module.argparse.Namespace(layer="points", sensitive_layer="secret", write_tool_check=True, wait_for_person=False)
        probe = probe_module.Probe(server.url, server.token)
        probe_module.run(probe, args)
        probe_module.write_outputs(probe, out)
        return probe, out, server

    def test_every_check_passes_and_the_token_never_reaches_the_evidence(self):
        probe, out, server = self.run_probe()
        failed = [c for c in probe.checks if not c[1]]
        self.assertEqual(failed, [], failed)
        self.assertEqual(len(probe.checks), 11)
        for name in ("mcp_probe.json", "mcp_probe.md"):
            self.assertNotIn(server.token, (Path(out) / name).read_text(encoding="utf-8"))

    def test_a_dead_server_is_reported_not_raised(self):
        dead = probe_module.Probe("http://127.0.0.1:1/mcp", "x")
        status, _reply = dead.rpc("ping")
        self.assertEqual(status, 0)

    def test_the_coordinate_detector(self):
        self.assertTrue(probe_module.looks_like_coordinates('{"geometry": {"type": "Point"}}'))
        self.assertTrue(probe_module.looks_like_coordinates("POINT (44.19 15.35)"))
        self.assertFalse(probe_module.looks_like_coordinates('{"feature_count": 5, "fields": ["name", "need"]}'))


class TestWorkflowFixtures(unittest.TestCase):
    def report(self, name):
        return checker.check_file(INPUTS / name, validate_one, workflow_module)

    def test_good_files_are_accepted_without_leaks(self):
        for name in ("smoke_reach.cgworkflow.json", "smoke_egress_stop.cgworkflow.json"):
            r = self.report(name)
            self.assertTrue(r["accepted"], (name, r["problems"]))
            self.assertEqual(r["leaks"], [], name)

    def test_the_fingerprint_the_sheet_promises_is_the_files_fingerprint(self):
        rows = json.loads((ROOT / "docs" / "HAND_TEST_V2_ROWS.json").read_text(encoding="utf-8"))["rows"]
        w9 = next(r for r in rows if r["id"] == "W9-import-good")
        self.assertIn(self.report("smoke_reach.cgworkflow.json")["fingerprint"], w9["pass_if"])

    def test_every_bad_file_is_refused_with_a_sentence(self):
        rows = json.loads((ROOT / "docs" / "HAND_TEST_V2_ROWS.json").read_text(encoding="utf-8"))["rows"]
        listed = next(r for r in rows if r["id"] == "W10-import-bad")["files"]
        self.assertEqual(sorted(listed), sorted(p.name for p in INPUTS.glob("bad_*.cgworkflow.json")))
        for name in listed:
            r = self.report(name)
            self.assertFalse(r["accepted"], name)
            self.assertTrue(r["problems"][0].endswith("."), name)

    def test_the_leak_scan_catches_what_an_export_must_never_hold(self):
        self.assertEqual(checker.leak_scan('{"url": "https://www.geoboundaries.org", "x": "C:/Users/a"}')[0][0], "absolute path")
        self.assertEqual([k for k, _ in checker.leak_scan('{"url": "https://www.geoboundaries.org"}')], [])
        self.assertTrue(checker.leak_scan('{"key": "sk-abcdefghijklmnopqrstuv"}'))
        self.assertTrue(checker.leak_scan("write to me@example.org"))
        self.assertTrue(checker.leak_scan("https://x.org/a?api_key=1"))


class TestRows(unittest.TestCase):
    def test_every_w_row_says_what_goes_in_what_comes_out_and_how_to_judge(self):
        rows = [r for r in json.loads((ROOT / "docs" / "HAND_TEST_V2_ROWS.json").read_text(encoding="utf-8"))["rows"] if r["id"].startswith("W")]
        self.assertGreaterEqual(len(rows), 12)
        for r in rows:
            for key in ("inputs", "outputs", "pass_if", "cost", "evidence", "expect"):
                self.assertTrue(r.get(key, "").strip(), (r["id"], key))
            for name in r.get("files", []):
                self.assertTrue((INPUTS / name).is_file(), name)

    def test_the_bundle_carries_the_tools_and_fixtures(self):
        builder = load("build_hand_test_v2")
        for tool in builder.TOOLS_FOLDER:
            self.assertTrue((ROOT / "tools" / tool).is_file(), tool)


if __name__ == "__main__":
    unittest.main()


class TestEvidenceReader(unittest.TestCase):
    def test_it_lists_the_records_each_layer_holds_and_the_probes_failed_checks(self):
        reader = load("check_evidence")
        folder = Path(tempfile.mkdtemp())
        (folder / "evidence" / "W2").mkdir(parents=True)
        (folder / "evidence" / "W2" / "layer_properties.json").write_text(json.dumps({"Yemen": {"cartogen/checks": [1], "cartogen/sources": [2]}}), encoding="utf-8")
        (folder / "o" / "W6").mkdir(parents=True)
        (folder / "o" / "W6" / "mcp_probe.json").write_text(json.dumps({"checks": [{"id": "P1a", "ok": True}, {"id": "P3", "ok": False}]}), encoding="utf-8")
        self.assertEqual(reader.record_lines(folder), ["  W2: Yemen: checks, sources", "  W6: mcp probe 1 of 2 passed; FAILED P3"])
