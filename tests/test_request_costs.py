"""tools/request_costs.py (master-list row LR-24): calls, first tool and tokens per request, read from the evidence folders the plugin writes.
No QGIS. The folders in these tests are made by the plugin's own EvidenceRecorder, so a change to its file format breaks this test, not the next live run."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import request_costs as rc  # noqa: E402

from cartogen_ai.core.agent.evidence import EvidenceRecorder  # noqa: E402

ROUTING = json.loads((ROOT / "tests" / "fixtures" / "routing_requests.json").read_text(encoding="utf-8"))
USAGE = "This turn: 5 calls, 131,878 input (51,200 cached) + 2,100 output tokens; last call 27,400 input"


def record(root, stamp, request, tools, usage=USAGE):
    recorder = EvidenceRecorder(str(Path(root) / "cartogen_evidence" / stamp), request)
    for name in tools:
        recorder.record_call(name, {"layer_name": "x"}, {"success": True}, 12)
    recorder.finish("done", usage_line=usage)


class TestParsing(unittest.TestCase):
    def test_the_usage_line_the_plugin_writes_is_read_back(self):
        self.assertEqual(rc.parse_usage(USAGE), {"model_calls": 5, "input_tokens": 131878, "cached_tokens": 51200, "output_tokens": 2100})
        self.assertEqual(rc.parse_usage(""), {})
        self.assertEqual(rc.parse_usage("This turn: 2 calls, 10 input (0 cached) + 5 output tokens; 1 call(s) reported no usage")["input_tokens"], 10)

    def test_tool_names_keep_call_order_and_skip_bad_lines(self):
        text = '{"tool": "a"}\nnot json\n{"tool": "b"}\n{"n": 3}\n'
        self.assertEqual(rc.tool_names(text), ["a", "b"])


class TestJudging(unittest.TestCase):
    def test_a_c26_request_must_start_with_a_tool_its_routing_row_accepts(self):
        request = "Public health: Find the statistically significant hot spots of cases by district"
        self.assertEqual(rc.judge(request, ["analyze_hotspots_gi_star"], ROUTING)[0], "ok")
        verdict, reason = rc.judge(request, ["search_web", "analyze_hotspots_gi_star"], ROUTING)
        self.assertEqual(verdict, "over target")
        self.assertIn("first tool was search_web", reason)
        self.assertEqual(rc.judge(request, [], ROUTING)[0], "over target")

    def test_a_chart_request_over_the_call_budget_is_flagged(self):
        request = "Make a bar chart of the clinics by district"
        self.assertEqual(rc.judge(request, ["chart_field_by_category"], ROUTING)[0], "ok")
        self.assertEqual(rc.judge(request, ["x"] * (rc.CHART_CALL_BUDGET + 1), ROUTING)[0], "over target")

    def test_any_other_request_is_listed_but_not_judged(self):
        self.assertEqual(rc.judge("Buffer the roads by 50 metres", ["buffer_analysis"], ROUTING)[0], "not judged")


class TestReport(unittest.TestCase):
    def test_a_run_with_three_requests_gives_one_row_each_with_the_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            record(tmp, "20261122_090000", "Public health: Is this cluster of cases real or just chance?", ["detect_spatial_clusters"])
            record(tmp, "20261122_090100", "Make a bar chart of cases", ["a", "b", "c", "d"], usage="")
            record(tmp, "20261122_090200", "Buffer the roads", ["buffer_analysis"])
            rows = rc.read_requests(tmp)
            self.assertEqual([len(r["tools"]) for r in rows], [1, 4, 1])
            self.assertEqual(rows[0]["usage"]["input_tokens"], 131878)
            self.assertEqual(rows[1]["usage"], {})
            report = rc.build_report(rows, ROUTING)
        self.assertIn("3 request(s); 1 over target.", report)
        self.assertIn("detect_spatial_clusters", report)
        self.assertIn("4 tool calls for a chart request", report)

    def test_no_evidence_says_how_to_get_some(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = rc.build_report(rc.read_requests(tmp), ROUTING)
        self.assertIn("save the project first", report)

    def test_the_twelve_c26_requests_are_all_matched_by_a_routing_row(self):
        card = json.loads((ROOT / "docs" / "FULL_SMOKE_ROWS.json").read_text(encoding="utf-8"))["rows"]
        do = next(r for r in card if r["id"] == "C26-r2-routing")["do"]
        requests = [m.group(1).strip() for m in __import__("re").finditer(r"\d+\. ((?:Public health|Public safety|Humanitarian|Urban planning|Environment|Real estate):.*?)(?=\s{2}\d+\. |$)", do)]
        self.assertEqual(len(requests), 12)
        for request in requests:
            self.assertIsNotNone(rc.expected_first_tools(request, ROUTING), request)


if __name__ == "__main__":
    unittest.main()
