"""Routing requests kept as data (tests/fixtures/routing_requests.json): a wording the router missed is added as a row with
`python tools/routing_golden.py add`, not by editing a Python table. Each row lists tools that must be offered; a list inside means any one of
them is enough. Complements the code tables in test_tool_router_basics.py, which stay."""
import json
import unittest
from pathlib import Path

from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
from cartogen_ai.core.services.tool_router import ToolRouter

DATA = Path(__file__).resolve().parent / "fixtures" / "routing_requests.json"
ROWS = json.loads(DATA.read_text(encoding="utf-8"))


def missing_tools():
    router = ToolRouter(TOOLS_SCHEMA)
    problems = []
    for row in ROWS:
        offered = {t["function"]["name"] for t in router.filter_relevant_tools(row["prompt"])}
        for need in row["tools"]:
            options = set(need) if isinstance(need, list) else {need}
            if not options & offered:
                problems.append(f"{row['prompt']!r}: none of {sorted(options)} offered")
    return problems


class TestRoutingRequestsData(unittest.TestCase):
    def test_every_request_is_offered_its_tools(self):
        self.assertEqual(missing_tools(), [])

    def test_every_named_tool_is_registered(self):
        registered = {t["function"]["name"] for t in TOOLS_SCHEMA}
        for row in ROWS:
            for need in row["tools"]:
                for name in (need if isinstance(need, list) else [need]):
                    self.assertIn(name, registered, row["prompt"])

    def test_size_pin(self):
        self.assertGreaterEqual(len(ROWS), 27)  # raise when you add rows; never lower it without a stated reason


if __name__ == "__main__":
    unittest.main()
