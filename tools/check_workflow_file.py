#!/usr/bin/env python3
"""Checks a .cgworkflow.json file the plugin exported (or one a tester edited), so the export and import rows need no manual reading of JSON (PLAN-050).

    python tools/check_workflow_file.py FILE [FILE ...] [--expect-valid | --expect-invalid] [--json OUT.json]

For each file it reports: whether the plugin's own validator accepts it (and its problems and warnings), its SHA-256 fingerprint, the tool names in
order, and a LEAK SCAN of the raw text for what an export must never hold: absolute paths, URLs with a query or key, API-key-shaped strings, email
addresses, long coordinate lists. Needs the repository (it imports the plugin's validator; no QGIS). Exit 1 when an expectation is not met:
--expect-valid fails on any validator problem or leak, --expect-invalid fails when the file is accepted. With neither, it only reports."""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

LEAKS = {
    "absolute path": re.compile(r"(?:(?<![A-Za-z])[A-Za-z]:(?:\\{1,2}|/)|\"/(?:home|Users|tmp|var|mnt)/)"),
    "api key shape": re.compile(r"(?:sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{20,}|Bearer\s+[A-Za-z0-9._-]{16,}|api[_-]?key\"?\s*[:=])", re.I),
    "email address": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "url with query or key": re.compile(r"https?://[^\s\"]*[?&](?:key|token|api_key|apikey|secret)=", re.I),
    "coordinate list": re.compile(r"(?:-?\d{1,3}\.\d{4,}\s*,\s*){3,}"),
}


def leak_scan(text):
    """[(kind, snippet)] for each leak shape found in the raw file text. Pure."""
    found = []
    for kind, pattern in LEAKS.items():
        match = pattern.search(text)
        if match:
            start = max(0, match.start() - 20)
            found.append((kind, text[start:match.end() + 20].replace("\n", " ")))
    return found


def validator():
    import cartogen_ai.core.agent.agent_orchestrator  # noqa: F401  (registers every tool)
    from cartogen_ai.core import tool_operations
    from cartogen_ai.core.agent import workflow_file
    from cartogen_ai.core.agent.tools.registry import TOOLS_SCHEMA
    schemas = workflow_file.schemas_from(TOOLS_SCHEMA)
    return workflow_file, lambda source: workflow_file.validate(source, schemas, tool_operations.get_tool_operation_type)


def check_file(path, validate, module):
    """The report dict for one file. Pure given the validator."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    document, problems, warnings = validate(text)
    return {
        "file": str(path), "accepted": not problems, "problems": list(problems), "warnings": list(warnings),
        "fingerprint": module.fingerprint(document) if document else None,
        "tools": [s.get("tool") for s in (document or {}).get("steps", [])],
        "leaks": leak_scan(text),
    }


def main(argv):
    files = [a for a in argv[1:] if not a.startswith("--") and argv[argv.index(a) - 1] != "--json"]
    if not files:
        raise SystemExit(__doc__)
    module, validate = validator()
    reports = [check_file(f, validate, module) for f in files]
    bad = False
    for r in reports:
        print(f"{r['file']}: {'ACCEPTED' if r['accepted'] else 'REFUSED'}; steps: {', '.join(r['tools']) or 'none'}")
        print(f"  fingerprint {r['fingerprint']}")
        for p in r["problems"]:
            print(f"  problem: {p}")
        for w in r["warnings"]:
            print(f"  warning: {w}")
        for kind, snippet in r["leaks"]:
            print(f"  LEAK ({kind}): ...{snippet}...")
        if "--expect-valid" in argv and (not r["accepted"] or r["leaks"]):
            bad = True
        if "--expect-invalid" in argv and r["accepted"]:
            print("  EXPECTED REFUSAL BUT THE FILE WAS ACCEPTED")
            bad = True
    if "--json" in argv:
        Path(argv[argv.index("--json") + 1]).write_text(json.dumps(reports, indent=1), encoding="utf-8")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
