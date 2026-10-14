"""Write tests/fixtures/tool_schema_snapshot.json from the live tool registry.

Run it (python tools/snapshot_tool_schema.py) only when a tool or parameter was ADDED on purpose; the snapshot test
(tests/test_tool_schema_snapshot.py) fails on any removal or rename, which is the regression it exists to catch."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))


def current_snapshot():
    from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
    snap = {}
    for entry in TOOLS_SCHEMA:
        fn = entry.get("function", entry)
        params = fn.get("parameters", {}) or {}
        snap[fn["name"]] = {"properties": sorted((params.get("properties") or {}).keys()),
                            "required": sorted(params.get("required") or [])}
    return snap


if __name__ == "__main__":
    path = os.path.join(ROOT, "tests", "fixtures", "tool_schema_snapshot.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(current_snapshot(), fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"wrote {len(current_snapshot())} tools to {path}")
