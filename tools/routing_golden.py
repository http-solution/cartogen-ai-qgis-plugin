"""Add or check routing requests without editing Python: `add "<request>" tool1,tool2` appends a row to tests/fixtures/routing_requests.json,
`check` offers each request to the router and lists the tools it did not offer. A tool name inside `|` means any one of them is enough
(`ingest_osm_features|fetch_osm_features`). Rows are append-only: the size pin in tests/test_golden_suite_size_pins.py stops deletions."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests" / "fixtures" / "routing_requests.json"


def _load():
    return json.loads(DATA.read_text(encoding="utf-8"))


def _save(rows):
    DATA.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv):
    if len(argv) >= 3 and argv[0] == "add":
        tools = [t.split("|") if "|" in t else t for t in argv[2].split(",")]
        rows = _load()
        rows.append({"prompt": argv[1], "tools": tools, "source": argv[3] if len(argv) > 3 else "added by tools/routing_golden.py"})
        _save(rows)
        print(f"added; {len(rows)} rows. Run: python tools/routing_golden.py check")
        return 0
    if argv[:1] == ["check"]:
        sys.path[:0] = [str(ROOT), str(ROOT / "src")]
        from tests.test_routing_requests_data import missing_tools
        problems = missing_tools()
        print("\n".join(problems) if problems else f"all {len(_load())} requests offered their tools")
        return 1 if problems else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
