"""Review sheet for the Arabic and French routing phrases (ML-1), and the importer for the reviewed sheet.

Why: core/services/routing_languages.json holds the Arabic and French words that make a tool get offered ("اعرض المستشفيات" -> the OSM tool).
They were written by the assistant and have not been read by a fluent speaker, and a wrong or odd phrase either never matches or pulls the
wrong tool. A reviewer should not need to open JSON or know tool names, so this writes a plain CSV: for every phrase, what the tool does in
English, with empty columns to mark it. It also reads the marked sheet back.

    python tools/language_review.py export SHEET.csv      # write the sheet (UTF-8 with a BOM, opens correctly in Excel)
    python tools/language_review.py apply SHEET.csv       # apply the marked sheet to routing_languages.json
    python tools/language_review.py apply SHEET.csv --dry-run

Sheet columns: language, tool, what_it_does, phrase, verdict, correction, note.
  verdict  OK (or empty)  keep as is
           FIX            replace `phrase` with `correction`
           REMOVE         drop the phrase
           ADD            add `correction` as a new phrase for this tool and language (use a row with an empty `phrase`)
`apply` refuses a sheet that would leave a tool with no phrase in one language (the two languages must cover the same tools), names a tool
that is not registered, or adds a phrase too short to match safely (3 letters or fewer once folded), and changes nothing in that case."""
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "cartogen_ai" / "core" / "services" / "routing_languages.json"
COLUMNS = ["language", "tool", "what_it_does", "phrase", "verdict", "correction", "note"]
VERDICTS = {"", "OK", "FIX", "REMOVE", "ADD"}


def _tool_descriptions():
    sys.path[:0] = [str(ROOT / "src")]
    from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
    out = {}
    for tool in TOOLS_SCHEMA:
        fn = tool["function"]
        text = re.sub(r"\s*\([^)]*\)", "", " ".join(fn.get("description", "").split()))     # drop "(e.g. ...)" so it cannot end the sentence
        out[fn["name"]] = re.split(r"(?<=[a-z0-9])[.!?]\s", text, maxsplit=1)[0][:160]
    return out


def _load():
    return json.loads(DATA.read_text(encoding="utf-8"))


def _save(table):
    DATA.write_text(json.dumps(table, indent=1, ensure_ascii=False), encoding="utf-8")


def export_rows(table=None, descriptions=None):
    """One row per phrase, ordered by language then tool. Pure given its two inputs."""
    table = table or _load()
    descriptions = descriptions if descriptions is not None else _tool_descriptions()
    rows = []
    for lang in sorted(table):
        for tool, phrases in table[lang].items():
            rows.extend({"language": lang, "tool": tool, "what_it_does": descriptions.get(tool, ""), "phrase": phrase,
                         "verdict": "", "correction": "", "note": ""} for phrase in phrases)
    return rows


def apply_rows(table, rows, registered, folded_len):
    """(new table, problems). `problems` non-empty means nothing may be written. Pure: `registered` is the set of tool names and
    `folded_len` the router's fold-then-length function."""
    new = {lang: {tool: list(phrases) for tool, phrases in tools.items()} for lang, tools in table.items()}
    problems = []
    for number, row in enumerate(rows, start=2):                      # row 1 of the sheet is the header
        lang, tool = (row.get("language") or "").strip(), (row.get("tool") or "").strip()
        verdict = (row.get("verdict") or "").strip().upper()
        phrase, fix = (row.get("phrase") or "").strip(), (row.get("correction") or "").strip()
        where = f"row {number} ({lang} {tool})"
        if verdict not in VERDICTS:
            problems.append(f"{where}: unknown verdict {verdict!r}")
            continue
        if verdict in ("", "OK"):
            continue
        if lang not in new or tool not in registered:
            problems.append(f"{where}: unknown language or tool")
            continue
        phrases = new[lang].setdefault(tool, [])
        if verdict in ("FIX", "ADD") and (not fix or folded_len(fix) < 3):
            problems.append(f"{where}: the correction is empty or too short to match safely")
            continue
        if verdict in ("FIX", "REMOVE") and phrase not in phrases:
            problems.append(f"{where}: phrase {phrase!r} is not in the file")
            continue
        if verdict in ("FIX", "REMOVE"):
            phrases.remove(phrase)
        if verdict in ("FIX", "ADD") and fix not in phrases:
            phrases.append(fix)
    for tools in new.values():
        for tool, phrases in list(tools.items()):
            if not phrases:
                del tools[tool]
    covered = [set(tools) for tools in new.values()]
    if not problems and any(c != covered[0] for c in covered):
        problems.append("the languages no longer cover the same tools: " + ", ".join(sorted(set.union(*covered) - set.intersection(*covered))))
    return new, problems


def main(argv):
    if len(argv) >= 2 and argv[0] == "export":
        rows = export_rows()
        with open(argv[1], "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        print(f"wrote {len(rows)} phrases to {argv[1]}")
        return 0
    if len(argv) >= 2 and argv[0] == "apply":
        sys.path[:0] = [str(ROOT / "src")]
        from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
        from cartogen_ai.core.services.tool_router import fold
        with open(argv[1], encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        registered = {t["function"]["name"] for t in TOOLS_SCHEMA}
        new, problems = apply_rows(_load(), rows, registered, lambda text: len(fold(text).strip()))
        if problems:
            print("NOT applied:\n  " + "\n  ".join(problems))
            return 1
        before = _load()
        added = sum(len(p) for t in new.values() for p in t.values()) - sum(len(p) for t in before.values() for p in t.values())
        if "--dry-run" in argv:
            print(f"dry run: would apply (net {added:+d} phrases)")
            return 0
        _save(new)
        print(f"applied (net {added:+d} phrases); run the tests: python -m unittest tests.test_tool_keywords tests.test_routing_requests_data")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
