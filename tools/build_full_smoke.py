#!/usr/bin/env python3
"""Builds the FULL live smoke package (PLAN-056): one zip that covers every ledger entry that is not verified by hand.

    python tools/build_full_smoke.py --plugin-zip dist/cartogen_ai_v<version>.zip [--out-dir DIR]

Output: <out-dir or dist>/cartogen_ai_full_smoke_<version>.zip. Contents (all under one top folder):
  README_FIRST.txt        what to do, in order, on one page
  EVIDENCE_HOWTO.txt      where evidence goes and the two lines that collect it
  FAILURE_PROTOCOL.md     what to capture when a row fails, and the diagnostic block for the notes
  COVERAGE.md            every ledger entry -> the row that covers it (or why a person cannot test it)
  1_plugin/               the plugin zip and its SHA-256
  2_layout_check/         the model-free layout script (row A1)
  3_SHEET.md              the rows, by session, each with Starts from / Do / Expect / Save / Needs / Inputs
  3_ROWS.json             the same rows as data (5_check_evidence.py reads it)
  3_test_files/           EVERY input a row names (checked at build time: a missing file stops the build)
  EVIDENCE_TABLE.md       per row: needs, input files, evidence to save, pass condition
  4_RESULTS.csv           one line per row to fill in
  5_check_evidence.py     reads the returned folder and prints a verdict per row
  6_tools/                collect_evidence.py (QGIS console), mcp_probe.py, check_workflow_file.py, summarize_usage_log.py
  results/                evidence/<row>/CHECKLIST.txt per row, outputs/, screens/, logs/
The 22 rows of docs/HAND_TEST_V2_ROWS.json are included unchanged; the new rows are in docs/FULL_SMOKE_ROWS.json.

    --only ID,ID,...   or   --only @docs/ROUND2_ROWS.json   [--label round2]
builds a package of just those rows (PLAN-059, round 2): the zip is named cartogen_ai_full_smoke_<version>_<label>.zip, 3_ROWS.json, 4_RESULTS.csv, COVERAGE.md and the
results folders hold only those rows, and only the files they name are required. Coverage of the FULL set is still checked first, so a subset cannot hide a gap."""
import hashlib
import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_hand_test_v2 as v2          # (same folder; reuses the checklist text, version and fixture folders)
import make_full_smoke_fixtures as fixtures

REPO = v2.REPO
FULL_ROWS = REPO / "docs" / "FULL_SMOKE_ROWS.json"
LEDGER = REPO / "docs" / "FEATURE_LEDGER.json"
FIXTURE_TOKEN = re.compile(r"\b(?:smoke|before|after)_[A-Za-z0-9_]*\.(?:qgz|gpkg|tif|csv|pdf|docx|asc|prj|geojson|2dm|json)\b")
TOOLS_FOLDER = (*v2.TOOLS_FOLDER, "verify_inputs.py")


def load():
    return json.loads(FULL_ROWS.read_text(encoding="utf-8"))


def all_rows(doc=None):
    """The combined rows in running order: session A to F; inside a session the new rows first, then the v2 rows. Each has session and covers. Pure."""
    doc = doc or load()
    combined = []
    for index, row in enumerate(doc["rows"]):
        combined.append((row["session"], 0, index, row))
    for index, row in enumerate(v2.rows()):
        extra = doc["v2_rows"][row["id"]]
        merged = dict(row, session=extra["session"], covers=list(extra["covers"]))
        for field, added in (doc.get("v2_overrides", {}).get(row["id"]) or {}).items():           # text APPENDED to a v2 row's field; the v2 rows file stays as it was
            merged[field] = str(merged.get(field, "")) + added
        combined.append((extra["session"], 1, index, merged))
    return [row for _s, _k, _i, row in sorted(combined, key=lambda item: item[:3])]


def ledger_not_verified():
    """The ids of the ledger entries that are not verified by hand, by the dashboard's own (conservative) rule. Pure given the files."""
    sys.path.insert(0, str(REPO / "tools"))
    import dashboard_snapshot
    features = json.loads(LEDGER.read_text(encoding="utf-8"))["features"]
    return [f["id"] for f in features if dashboard_snapshot.ledger_class(f.get("hand_verified")) != "Verified by hand"]


def coverage_problems(rows, doc, ledger_ids):
    """[problem sentence] for ledger entries nobody covers, covered twice by nobody-testable, or named but unknown. Empty means every one is accounted for. Pure."""
    covered = {i for row in rows for i in row["covers"]}
    nht = set(doc["not_hand_testable"])
    problems = [f"{i}: covered by no row and not listed as not hand-testable" for i in ledger_ids if i not in covered and i not in nht]
    problems += [f"{i}: named by a row but it is not an unverified ledger entry" for i in sorted(covered - set(ledger_ids))]
    problems += [f"{i}: listed as not hand-testable but it is not an unverified ledger entry" for i in sorted(nht - set(ledger_ids))]
    problems += [f"{i}: both covered by a row and listed as not hand-testable" for i in sorted(covered & nht)]
    return problems


def coverage_page(rows, doc, ledger_ids, features):
    by_id = {f["id"]: f for f in features}
    owner = {}
    for row in rows:
        for i in row["covers"]:
            owner.setdefault(i, []).append(row["id"])
    out = ["# Coverage: every ledger entry that is not verified by hand\n",
           f"{len(ledger_ids)} entries. {len(owner)} are covered by at least one row; {len(doc['not_hand_testable'])} cannot be tested by a person (reason given).\n",
           "| Ledger entry | Row(s) | What it is |", "|---|---|---|"]
    for i in ledger_ids:
        what = by_id[i]["feature"].replace("|", "/").replace("\n", " ")[:110]
        if i in owner:
            out.append(f"| {i} | {', '.join(owner[i])} | {what} |")
        else:
            out.append(f"| {i} | NOT HAND-TESTABLE: {doc['not_hand_testable'][i]} | {what} |")
    return "\n".join(out) + "\n"


def build_note(plugin_zip, digest, v):
    """1_plugin/BUILD.txt: which commit the plugin zip was built from and its checksum. The version stays 1.18.5 while 1.18.6 is held, so an older 1.18.5 on the
    tester's machine would otherwise look identical. Never raises: an unreadable git state is written as 'unknown'."""
    import subprocess
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()   # noqa: S607 -- fixed argv
    except Exception:                                    # the note is advice; a missing git must not stop the build
        commit = "unknown"
    return (f"plugin zip: {plugin_zip.name}\ncommit: {commit}\nsha256: {digest}\n\n"
            f"The plugin keeps the same version number ({v}) as the build you may already have installed, because the next release is held. Install THIS zip over it "
            "(Plugins > Manage and Install Plugins > Install from ZIP), restart QGIS, and compare the SHA-256 of the zip you installed with the line above before "
            "you start. If it differs, you are not testing this build.\n")


def parse_only(arg):
    """The row ids of `--only`: a comma list ('A1-layout-script,V4-animate') or '@path' to a JSON file whose "rows" is an object keyed by row id. Pure given the file."""
    if arg.startswith("@"):
        return list(json.loads(Path(arg[1:]).read_text(encoding="utf-8"))["rows"])
    return [part.strip() for part in arg.split(",") if part.strip()]


def select_rows(rows, only):
    """The rows named in `only`, in the sheet's running order. Refuses an empty list and any id that is not a row (named, never ignored). Pure."""
    if not only:
        raise SystemExit("--only names no rows")
    known = {row["id"] for row in rows}
    unknown = [i for i in only if i not in known]
    if unknown:
        raise SystemExit("--only names rows that do not exist: " + ", ".join(unknown))
    chosen = set(only)
    return [row for row in rows if row["id"] in chosen]


def subset_coverage_page(rows, features):
    """COVERAGE.md for a subset package: the ledger entries these rows cover, and which row covers each. Pure."""
    by_id = {f["id"]: f for f in features}
    owner = {}
    for row in rows:
        for i in row["covers"]:
            owner.setdefault(i, []).append(row["id"])
    out = [f"# Coverage: the ledger entries these {len(rows)} rows cover\n",
           f"{len(owner)} entries. This is a subset package (see README_FIRST.txt): the rest of the ledger is in the full package.\n",
           "| Ledger entry | Row(s) | What it is |", "|---|---|---|"]
    for i in sorted(owner):
        what = by_id[i]["feature"].replace("|", "/").replace("\n", " ")[:110] if i in by_id else ""
        out.append(f"| {i} | {', '.join(owner[i])} | {what} |")
    return "\n".join(out) + "\n"


def evidence_table(rows, v):
    """EVIDENCE_TABLE.md: for every row, in running order, what it needs, which input files it uses and exactly what evidence to save, on one page that can be read
    without opening 3_SHEET.md. Asked for by the owner on 2026-11-07 ('mention on each row what evidence is needed'). Pure."""
    out = [f"# Cartogen AI {v} - what each row needs and what evidence to save\n",
           "Read EVIDENCE_HOWTO.txt once (3 minutes) and FAILURE_PROTOCOL.md before the first row. The rows are in running order; 3_SHEET.md has the full steps.\n",
           ("**For EVERY row, whatever the result:** run `snap('<row id>')` in the QGIS Python console right after the reply (never in the chat), write Pass / Partial / Fail / Skip "
            "and one line of notes in 4_RESULTS.csv, and take the screenshots the row names. **If a row fails or looks wrong:** screenshot first, then `snap`, then the rest of "
            "FAILURE_PROTOCOL.md, before you retry anything.\n")]
    for row in rows:
        files = row.get("files") or []
        inputs = v2.fill(row["inputs"], v) if row.get("inputs") else ""
        given = "; ".join(x for x in ((", ".join(files)) if files else "", inputs) if x) or "none: no file from 3_test_files is named for this row (what you need is in 'Starts from' and in 3_SHEET.md)"
        out += [f"## {row['id']}: {v2.fill(row['title'], v)}", "",
                f"- **You need:** {row['needs']}",
                f"- **Starts from:** {v2.fill(row['starts_from'], v)}",
                f"- **Input files (in 3_test_files):** {given}",
                f"- **Evidence to save:** {v2.fill(row['evidence'], v)}",
                f"- **Pass when:** {v2.fill(row.get('pass_if') or row['expect'], v)}", ""]
    return "\n".join(out)


def sheet(rows, doc, v):
    out = [f"# Cartogen AI {v} - full live smoke test\n",
           "Run the sessions in order (A to F). Each row starts from the state it names; none depends on another. Needs = what you must have for that row.\n"]
    last = None
    for row in rows:
        if row["session"] != last:
            last = row["session"]
            out += [f"\n## Session {doc['sessions'][last]}\n"]
        out += [f"### {row['id']}: {v2.fill(row['title'], v)}", "",
                f"- **Covers:** {', '.join(row['covers']) or 'documentation only'}", f"- **Needs:** {row['needs']}",
                f"- **Starts from:** {v2.fill(row['starts_from'], v)}", f"- **Do:** {v2.fill(row['do'], v)}",
                f"- **Expect:** {v2.fill(row['expect'], v)}", f"- **Save:** {v2.fill(row['evidence'], v)}"]
        for key, label in (("inputs", "Inputs"), ("outputs", "Outputs"), ("pass_if", "Pass if"), ("cost", "Cost")):
            if row.get(key):
                out.append(f"- **{label}:** {v2.fill(row[key], v)}")
        if row.get("files"):
            out.append("- **Files (in 3_test_files):** " + ", ".join(row["files"]))
        out.append("")
    return "\n".join(out)


def readme(v, count, label=None):
    if label:
        # The round is named from the label ("round3" -> "ROUND 3"): this text said ROUND 2 for every subset until round 3 was built (2026-11-07).
        name = re.sub(r"ROUND(\d+)", r"ROUND \1", str(label).upper())
        head = (f"Cartogen AI {v} - live smoke test, {name} ({count} rows)\n"
                "=======================================================================\n\n"
                f"WHAT THIS IS: only the rows to run on THIS build ({count} rows, not the full {len(all_rows())}). Each row exists because a feature seen working live "
                "has since changed code, or a fix has never been seen working, or a case was never tested. 3_ROWS.json and COVERAGE.md say which. Row B4 (the most expensive) "
                "goes last and only if the provider has quota. Skip a row you cannot run and say why.\n\n")
    else:
        head = (f"Cartogen AI {v} - FULL live smoke test ({count} rows in 6 sessions)\n"
                "=======================================================================\n\n"
                "WHAT THIS IS: every feature in the ledger that is not yet verified by a person, as rows you can run. COVERAGE.md lists each feature and its row.\n\n")
    return (head +
            "1_plugin/            the plugin zip (SHA-256 in checksum_sha256.txt; BUILD.txt says which commit it is and how to be sure you installed it)\n"
            "2_layout_check/      the model-free layout script (row A1)\n"
            "3_SHEET.md           THE ROWS: read and run these, in order A to F\n"
            "3_test_files/        every input file a row names; open smoke_start.qgz from this folder (its data files sit beside it)\n"
            "EVIDENCE_TABLE.md    per row: what you need, the input files, exactly what evidence to save, and when it passes (one page; 3_SHEET.md has the full steps)\n"
            "4_RESULTS.csv        fill in the result of every row (Pass / Partial / Fail / Skip) and one line of notes\n"
            "EVIDENCE_HOWTO.txt   how to collect evidence: READ FIRST\n"
            "FAILURE_PROTOCOL.md  what to capture the moment a row fails (screenshot with clock, logs, input, steps) and the block to paste in the notes\n"
            "AGENT_PROMPT.md      the prompt to give an AI agent that runs this package for you\n"
            "results\\             one folder per row, each with a CHECKLIST.txt of what to save\n"
            "5_check_evidence.py  not for you: it reads what you send back\n"
            "6_tools/             collect_evidence.py (QGIS console), mcp_probe.py, check_workflow_file.py, verify_inputs.py (terminal), summarize_usage_log.py\n\n"
            "BEFORE YOU START\n"
            "  0. Terminal, in this folder:  python 6_tools/verify_inputs.py 3_test_files   (every input present and unchanged, or it names the file)\n"
            "  1. Install the plugin (see UPDATING below). Open QGIS.\n"
            "  2. In Cartogen Settings tick 'Save an evidence folder for each request'. Connect the model you will test (a hosted key or Ollama) in Connections.\n"
            "  3. Do the two evidence lines in EVIDENCE_HOWTO.txt once per QGIS session, in the QGIS Python console (never in the chat).\n"
            "SESSIONS (what each needs)\n"
            "  A  no model, no key: layout script, Settings, CLI (about 45 minutes)\n"
            "  B  chat routing: a real model (about 1 hour)\n"
            "  C  loading data, Stop, Undo: a real model\n"
            "  D  analysis, fetched data, checks, provenance: a real model and internet\n"
            "  E  privacy gates, layouts, exports: a real model\n"
            "  F  MCP server, workflow files, close-out: a terminal with Python 3.10+, optionally an MCP client\n"
            "  A row you cannot run (no key, no internet, no CLI): write Skip and why. Never leave it blank.\n"
            "AT THE END\n"
            "  python 5_check_evidence.py results      (row F3) and send back: the results folder, 4_RESULTS.csv, the cartogen_evidence folder.\n\n"
            + v2.fill(v2.UPDATE_STEPS, v))


EVIDENCE_PAGE = """HOW TO COLLECT EVIDENCE (read this once, 3 minutes)
=====================================================

WHERE IT GOES: the folder "results" in this package, already laid out:
  results\\evidence\\<row id>\\   one folder per row (A1-layout-script, B1-routing-plain, ...). Each has a CHECKLIST.txt: exactly what to put in it.
  results\\outputs\\<row id>\\    files a row makes (reports, exports, probe results). You copy them here.
  results\\screens\\            screenshots you take by hand, named as the row says (D1-borders.png ...).
  results\\logs\\               the CartogenAI log per row (written for you).

ONCE PER QGIS SESSION (after installing the plugin and opening the copy of smoke_start.qgz):
  1. In QGIS open Plugins > Python Console. Paste these two lines, with <bundle> replaced by the full path of this unzipped folder:
       exec(open(r"<bundle>\\6_tools\\collect_evidence.py", encoding="utf-8").read())
       begin(r"<bundle>")
     It prints "ready". In Cartogen Settings tick "Save an evidence folder for each request".

AFTER EACH ROW (about ten seconds):
  2. As soon as the reply is complete, type in the console:  snap('B1')   (the row's letter and number; two-part rows say snap('B3a') and snap('B3b'))
     It saves, into that row's folder: screenshots of the QGIS window and the map, the layer table, the plugin's records on every layer
     (layer_properties.json), the CartogenAI log, the project state, and the tools the plugin called (plugin_evidence). The reason for anything
     it could not save is in snap_errors.txt.
  3. Copy by hand what the row's CHECKLIST.txt lists: exported files into results\\outputs\\<row id>\\, screenshots into results\\screens\\.
  4. Write Pass / Partial / Fail / Skip and one line of notes in 4_RESULTS.csv. Never edit a saved file. If you could not save something, write "not saved: why".

THINGS THAT WENT WRONG IN THE FIRST RUN (2026-11-04), SO DO THESE:
  - WHERE TO TYPE: begin(), snap() and shot() are typed in QGIS's Python console (Plugins > Python Console), NEVER in the Cartogen chat. The first run sent
    snap('B1') to the model as a request.
  - FRESH CHAT: 1.18.5 has no "New chat" button. The conversation follows the project: start a row from File > New (or by opening the row's project file) and the chat
    starts empty. If the old conversation is still on screen after you switch, write that in the notes and carry on.
  - SAVE FIRST: save the project (File > Save As, into results\\outputs\\<row id>\\) BEFORE the first request. The plugin writes its evidence folder next to a saved project;
    an unsaved project leaves none and the row cannot be checked.
  - SCREENSHOTS AS FILES: in the console type  shot('D1-borders')  to save the QGIS window as results\\screens\\D1-borders.png (use the name the row gives).
  - A reply that does not repeat something the plugin recorded (a count of checks, a storage note, the 'why' of a ranking) is a Partial for the reply's wording, not a failure
    of the plugin: judge the plugin from the saved record (layer_properties.json, steps.jsonl) when the row says so.

ROWS THAT NEED NO QGIS CONSOLE: A1 prints its own folder; F-rows with mcp_probe.py, check_workflow_file.py and 5_check_evidence.py run in a normal terminal
(the row gives the command).

SENDING IT BACK: zip the whole "results" folder, and send it with 4_RESULTS.csv and the cartogen_evidence folder.
"""


def generated_files(tmp):
    fixtures.write_all(tmp)
    generated = {name: Path(tmp) / name for name in fixtures.FILES}
    sheet_path = Path(tmp) / "language_review_sheet.csv"
    import language_review
    code = language_review.main(["export", str(sheet_path)])           # the module's own command line, called in-process (it writes the sheet and returns 0)
    if code not in (0, None) or not sheet_path.is_file():
        raise SystemExit("tools/language_review.py could not write the review sheet")
    generated["language_review_sheet.csv"] = sheet_path
    return generated


def find_source(name, generated):
    for folder in (v2.INPUTS, v2.EXTRA_INPUTS):
        if (folder / name).is_file():
            return folder / name
    return generated.get(name)


def needed_files(rows, text):
    names = set(v2.PROJECT_FILES)
    for row in rows:
        names.update(row.get("files", []))
    in_folders = {Path(name).name for name in names if "/" in name}           # smoke_cod.json is shipped as cartogen_profiles/smoke_cod.json
    names.update(token for token in FIXTURE_TOKEN.findall(text) if token not in in_folders)
    return names


def main(argv):
    if "--plugin-zip" not in argv:
        raise SystemExit("usage: build_full_smoke.py --plugin-zip FILE.zip [--out-dir DIR] [--only ID,ID,... | --only @rows.json [--label NAME]]")
    plugin_zip = Path(argv[argv.index("--plugin-zip") + 1]).resolve()
    v = v2.version()
    if f"_v{v}.zip" not in plugin_zip.name:
        raise SystemExit(f"{plugin_zip.name} is not the {v} build")
    doc = load()
    rows = all_rows(doc)
    ledger_ids = ledger_not_verified()
    problems = coverage_problems(rows, doc, ledger_ids)         # always checked on the FULL set, so a subset can never hide a gap in the full package
    if problems:
        raise SystemExit("coverage is incomplete:\n  " + "\n  ".join(problems))
    subset = "--only" in argv
    label = (argv[argv.index("--label") + 1] if "--label" in argv else "subset") if subset else None
    if subset:
        rows = select_rows(rows, parse_only(argv[argv.index("--only") + 1]))
    text = sheet(rows, doc, v)
    stale = v2.stale_words(text)
    if stale:
        raise SystemExit(f"the sheet names {stale}, which went stale; fix the rows")
    features = json.loads(LEDGER.read_text(encoding="utf-8"))["features"]
    top = f"cartogen_ai_full_smoke_{v}" + (f"_{label}" if subset else "")
    out_dir = Path(argv[argv.index("--out-dir") + 1]).resolve() if "--out-dir" in argv else REPO / "dist"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{top}.zip"
    digest = hashlib.sha256(plugin_zip.read_bytes()).hexdigest()
    results = "id,session,title,covers,result (Pass/Partial/Fail/Skip),notes\n" + "".join(
        f"{r['id']},{r['session']},\"{v2.fill(r['title'], v).replace(chr(34), chr(39))}\",\"{' '.join(r['covers'])}\",,\n" for r in rows)
    combined = {"_about": doc["_about"], "rows": rows}
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        generated = generated_files(tmp)
        z.writestr(f"{top}/README_FIRST.txt", readme(v, len(rows), label if subset else None).replace("\n", "\r\n"))
        z.write(plugin_zip, f"{top}/1_plugin/{plugin_zip.name}")
        z.writestr(f"{top}/1_plugin/checksum_sha256.txt", f"{digest}  {plugin_zip.name}\n")
        z.writestr(f"{top}/1_plugin/BUILD.txt", build_note(plugin_zip, digest, v).replace("\n", "\r\n"))
        z.write(REPO / "tools" / "layout_check_script.py", f"{top}/2_layout_check/layout_check_script.py")
        for tool in TOOLS_FOLDER:
            z.write(REPO / "tools" / tool, f"{top}/6_tools/{tool}")
        z.writestr(f"{top}/3_SHEET.md", text)
        z.writestr(f"{top}/EVIDENCE_TABLE.md", evidence_table(rows, v))
        z.writestr(f"{top}/3_ROWS.json", json.dumps(combined, indent=1, ensure_ascii=False))
        z.writestr(f"{top}/4_RESULTS.csv", results)
        z.writestr(f"{top}/COVERAGE.md", subset_coverage_page(rows, features) if subset else coverage_page(rows, doc, ledger_ids, features))
        z.writestr(f"{top}/EVIDENCE_HOWTO.txt", EVIDENCE_PAGE.replace("\n", "\r\n"))
        z.write(REPO / "docs" / "FULL_SMOKE_AGENT_PROMPT.md", f"{top}/AGENT_PROMPT.md")          # for an AI agent that runs the package instead of a person
        z.write(REPO / "docs" / "FULL_SMOKE_FAILURE_PROTOCOL.md", f"{top}/FAILURE_PROTOCOL.md")
        z.write(REPO / "docs" / "WORKFLOW_FILES.md", f"{top}/3_test_files/WORKFLOW_FILES.md")
        for row in rows:
            z.writestr(f"{top}/results/evidence/{row['id']}/CHECKLIST.txt", v2.checklist(row, v))
            z.writestr(f"{top}/results/outputs/{row['id']}/PUT_OUTPUT_FILES_HERE.txt",
                       f"Files row {row['id']} makes go here (see ../../evidence/{row['id']}/CHECKLIST.txt).\r\n")
        z.writestr(f"{top}/results/screens/PUT_SCREENSHOTS_HERE.txt", "Screenshots a row asks for, named as the row says.\r\n")
        z.writestr(f"{top}/results/logs/WRITTEN_BY_SNAP.txt", "snap() writes one CartogenAI log per row here.\r\n")
        z.writestr(f"{top}/results/README.txt", "Everything the run produces goes here: evidence/, outputs/, screens/, logs/. How: see ../EVIDENCE_HOWTO.txt.\r\n")
        z.write(REPO / "tools" / "check_evidence.py", f"{top}/5_check_evidence.py")
        digests = {"WORKFLOW_FILES.md": hashlib.sha256((REPO / "docs" / "WORKFLOW_FILES.md").read_bytes()).hexdigest()}     # from the SOURCE files: see below
        shipped = set()
        for name in sorted(needed_files(rows, text)):
            source = find_source(name, generated)
            if source is None:
                raise SystemExit(f"a row names {name}, which is in no fixture folder and is not generated")
            z.write(source, f"{top}/3_test_files/{name}")
            digests[name] = hashlib.sha256(Path(source).read_bytes()).hexdigest()
            shipped.add(name)
        for folder in (v2.INPUTS, v2.EXTRA_INPUTS):                      # the pinned smoke inputs are all shipped: a row may use any of them
            for source in sorted(folder.iterdir()):
                if source.is_file() and source.name not in shipped and not source.name.endswith(".aux.xml"):
                    z.write(source, f"{top}/3_test_files/{source.name}")
                    digests[source.name] = hashlib.sha256(source.read_bytes()).hexdigest()
                    shipped.add(source.name)
        for name in sorted(set(generated) - shipped):
            z.write(generated[name], f"{top}/3_test_files/{name}")
            digests[name] = hashlib.sha256(Path(generated[name]).read_bytes()).hexdigest()
            shipped.add(name)
        # The sums come from the source files, never from reading the zip back while it is still being written: on Windows zipfile cannot read an entry just
        # added with write() (its name is kept with backslashes in memory and forward slashes in the file: BadZipFile 'File name in directory ... differ';
        # CI run of PR 569, 2026-11-04).
        sums = [f"{digests[name]}  {name}" for name in sorted(digests)]
        z.writestr(f"{top}/3_test_files/SHA256SUMS.txt", "\n".join(sums) + "\n")
    covered = len({i for row in rows for i in row["covers"]})
    print(f"wrote {out} ({out.stat().st_size // 1024} KB), {len(rows)} rows, " + (f"{covered} ledger entries covered (subset)" if subset else f"{len(ledger_ids)} ledger entries accounted for"))


if __name__ == "__main__":
    main(sys.argv)
