"""Builds the v2 hand-test bundle (PLAN-021 WP-G): the plugin zip, the model-free layout check script, a short generated sheet of the rows that
still need a person, the update steps, a results file, and the evidence checker. The version is read from metadata.txt, never typed.

    python tools/build_hand_test_v2.py --plugin-zip dist/cartogen_ai_v<version>.zip

Output: dist/cartogen_ai_hand_test_v2_<version>.zip"""
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROWS_FILE = REPO / "docs" / "HAND_TEST_V2_ROWS.json"
INPUTS = REPO / "docs" / "release_smoke_assets" / "inputs"          # the pinned smoke fixtures (docs/FULL_LIVE_TEST_rc34_INPUTS.sha256), never added to
EXTRA_INPUTS = REPO / "docs" / "hand_test_v2_inputs"                 # fixtures only the v2 rows use
FIXTURE_NAME = r"smoke_[A-Za-z_]+\.(?:qgz|gpkg|tif|csv|pdf|docx)"        # an input file a row names in its text; a row's `files` list names the others (workflow files)
PROJECT_FILES = ("smoke_start.qgz", "smoke_data.gpkg", "smoke_dem.tif", "smoke_image.tif")      # smoke_start.qgz opens layers by relative path from its own folder: all must ship beside it
TOOLS_FOLDER = ("collect_evidence.py", "mcp_probe.py", "check_workflow_file.py", "summarize_usage_log.py")      # 6_tools/: what the W rows run (PLAN-050)
STALE = ("1.16.1", "rc40", "rc39", "Task Manager")      # words that went stale in the 1.18.0 sheet; a row naming one is probably out of date


def version():
    for line in (REPO / "metadata.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("version="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("no version= in metadata.txt")


def rows():
    return json.loads(ROWS_FILE.read_text(encoding="utf-8"))["rows"]


def fill(text, v):
    return text.replace("{version}", v)


UPDATE_STEPS = """UPDATING AN EXISTING INSTALL (row V1-update)
  1. Write down the version you have now (Cartogen panel > Help shows "Version ...").
  2. Close every QGIS window except one. Save your project first.
  3. Plugins > Manage and Install Plugins > Install from ZIP, choose the file in 1_plugin, click Install Plugin. If QGIS asks to replace the
     installed plugin, say yes. Your provider and key are kept (they live in QGIS's own settings, not in the plugin folder).
  4. Close QGIS completely and open it again TWICE.
  5. Check: Help shows "Version {version}"; ONE Cartogen AI toolbar button; ONE Cartogen AI entry in the Plugins menu; ONE Cartogen panel
     (View > Panels). Open the Log Messages tab CartogenAI: no red lines.
  6. If you see two buttons, a missing panel or a red error: close QGIS, Settings > User Profiles > Open Active Profile Folder, go to python\\plugins,
     delete the Cartogen folder (cartogen_ai_plugin, or cartogen-ai in very old installs), open QGIS and install again from the zip. Write in the
     notes what happened BEFORE you deleted anything.
"""


def readme(v, row_count):
    return (f"Cartogen AI {v} - hand test v2 ({row_count} rows that need a person, plus one script that needs none)\n"
            "=====================================================================================\n\n"
            "1_plugin/            the plugin zip (SHA-256 in checksum_sha256.txt)\n"
            "2_layout_check/      layout_check_script.py: run it ONCE, it makes no model calls and costs nothing\n"
            "EVIDENCE_HOWTO.txt   HOW TO COLLECT EVIDENCE: where it goes and the two lines to paste in QGIS (read this FIRST)\n"
            "results\\             the evidence folders, one per row, each with a CHECKLIST.txt\n"
            "0_GUIDE.md           how to run the W rows: order, evidence layout, how each is judged (read this second)\n"
            "3_SHEET.md           the rows that still need you\n"
            "3_ROWS.json          the same rows as data (5_check_evidence.py reads it)\n"
            "3_test_files/        input data some rows use\n"
            "4_RESULTS.csv        fill in the result and notes\n"
            "5_check_evidence.py  not for you: it reads what you send back\n"
            "6_tools/             collect_evidence.py (QGIS console), mcp_probe.py and check_workflow_file.py (terminal), summarize_usage_log.py\n\n"
            "STEP A - the layout check (about two minutes, no API cost)\n"
            "  Install the plugin (see below), open QGIS, open the Python console (Plugins > Python Console), then type:\n"
            '     exec(open(r"<path to this folder>\\2_layout_check\\layout_check_script.py", encoding="utf-8").read())\n'
            "  It builds its own project, makes about a dozen layouts and exports them. When it finishes it prints PASS or FAIL for each check and\n"
            "  the folder it wrote (also in your temp folder). Send that whole folder back.\n\n"
            "STEP B - the rows in 3_SHEET.md (each starts from the state it names; none depends on another)\n"
            "  Tick 'Save an evidence folder for each request' in the Cartogen Settings first, and send the cartogen_evidence folder back.\n\n"
            "STEP C - evidence after each W row (about ten seconds per row). FULL INSTRUCTIONS: EVIDENCE_HOWTO.txt\n"
            "  Once per QGIS session, in the QGIS Python console (replace <this folder> with the full path of this unzipped folder):\n"
            "     exec(open(r\"<this folder>\\6_tools\\collect_evidence.py\", encoding=\"utf-8\").read())\n"
            "     begin(r\"<this folder>\")\n"
            "  After each W row's reply:  snap('W1a')  (use the name the row gives). It fills that row's folder under results\\evidence\\.\n"
            "  Then copy any output file the row's CHECKLIST.txt names into results\\outputs\\<row>\\ and any screenshot into results\\screens\\.\n\n"
            "STEP D - the terminal rows (W6, W7, W10, W8 check): run the scripts in 6_tools with plain Python 3.10+, not inside QGIS. The row gives the command.\n\n"
            "Send back: the layout_check folder, 4_RESULTS.csv, the cartogen_evidence folder, and any screenshots the rows ask for.\n\n"
            + fill(UPDATE_STEPS, v))


def checklist(row, v):
    """The text of results/evidence/<row>/CHECKLIST.txt: exactly what to put in this row's folders, in the order to do it. Pure."""
    lines = [f"ROW {row['id']}: {fill(row['title'], v)}", "",
             "1. Start from: " + fill(row["starts_from"], v), "2. Do: " + fill(row["do"], v), "3. Expect: " + fill(row["expect"], v), "",
             "SAVE (tick each when it is in the folder):",
             "  [ ] this folder: written for you by snap('<name>') in the QGIS Python console right after the reply: window.png, canvas.png, layers.txt,",
             "      layer_properties.json, log_cartogenai.txt, project.json, plugin_evidence/ (steps.jsonl = the tools called)",
             f"  [ ] as the row says: {fill(row['evidence'], v)}"]
    if row.get("outputs"):
        lines.append(f"  [ ] files this row makes -> copy into results\\outputs\\{row['id']}\\ : {fill(row['outputs'], v)}")
    lines += ["  [ ] screenshots -> results\\screens\\ named as the row says",
              "  [ ] result in 4_RESULTS.csv (Pass / Partial / Fail / Skip) and one line of notes", "",
              "PASS IF: " + fill(row.get("pass_if", "see Expect"), v), "COST: " + row.get("cost", "see the sheet")]
    return "\r\n".join(lines) + "\r\n"


EVIDENCE_PAGE = """HOW TO COLLECT EVIDENCE (read this once, 3 minutes)
=====================================================

WHERE IT GOES: the folder "results" in this bundle. It is already laid out:

  results\\evidence\\<row id>\\   one folder per row (W1-gate-on, W2-gate-fetch, ...). Each has a CHECKLIST.txt: exactly what to put in it.
  results\\outputs\\<row id>\\    files a row makes (reports, workflow files, probe results). You copy them here.
  results\\screens\\            screenshots you take by hand, named as the row says (W7-dialog.png ...).
  results\\logs\\               the CartogenAI log per row (written for you).

ONCE PER QGIS SESSION (after installing the plugin and opening the copy of smoke_start.qgz):
  1. In QGIS open Plugins > Python Console (the typing line at the bottom).
  2. Paste these two lines, with <bundle> replaced by the full path of this unzipped folder (keep the r and the quotes):
       exec(open(r"<bundle>\\6_tools\\collect_evidence.py", encoding="utf-8").read())
       begin(r"<bundle>")
     It prints "ready". In Cartogen Settings tick "Save an evidence folder for each request".

AFTER EACH ROW (about ten seconds):
  3. As soon as the reply is complete, type in the console:  snap('W1a')   (the name the row gives; W2 rows use snap('W2'))
     It saves, into that row's folder: a screenshot of the QGIS window and of the map, the layer table, the plugin's own records on every layer
     (layer_properties.json), the CartogenAI log, the project state, and the tools the plugin called (plugin_evidence).
     It prints what was saved and what it could not save (the reason is in snap_errors.txt).
  4. Copy by hand what the row's CHECKLIST.txt lists: output files into results\\outputs\\<row id>\\, screenshots into results\\screens\\.
  5. Write Pass / Partial / Fail / Skip and one line of notes in 4_RESULTS.csv.
  Never edit a saved file. A thing you could not save: write "not saved: why" in the notes.

ROWS THAT NEED NO QGIS CONSOLE: W6, W7, W10 run scripts in a normal terminal; their output goes straight to results\\outputs\\<row id>\\ (the row gives the command).

AT THE END:
  6. python 5_check_evidence.py results     (reads everything and prints a verdict per row; paste its text into your reply)
  7. Zip the whole "results" folder and send it back with 4_RESULTS.csv and the saved CartogenAI log.
"""


def sheet(v):
    out = [f"# Cartogen AI {v} - hand test v2\n",
           ("Only what needs a person, a real model or your computer's fonts. The layout script (STEP A in README_FIRST.txt) covers footer, legend, "
            "page sizes, names, presets, profile, logo and sign-off by measurement and exports the pages for you to look at.\n")]
    for row in rows():
        out += [f"### {row['id']} ({row['issue']}): {fill(row['title'], v)}", "",
                f"- **Starts from:** {fill(row['starts_from'], v)}", f"- **Do:** {fill(row['do'], v)}",
                f"- **Expect:** {fill(row['expect'], v)}", f"- **Save:** {fill(row['evidence'], v)}", f"- **Needs:** {row['needs']}"]
        for key, label in (("inputs", "Inputs"), ("outputs", "Outputs"), ("pass_if", "Pass if"), ("cost", "Cost")):
            if row.get(key):
                out.append(f"- **{label}:** {fill(row[key], v)}")
        out.append("")
    return "\n".join(out)


def stale_words(text):
    return [w for w in STALE if w in text]


def main():
    if "--plugin-zip" not in sys.argv:
        raise SystemExit("usage: build_hand_test_v2.py --plugin-zip FILE.zip")
    plugin_zip = Path(sys.argv[sys.argv.index("--plugin-zip") + 1]).resolve()
    v = version()
    if f"_v{v}.zip" not in plugin_zip.name:
        raise SystemExit(f"{plugin_zip.name} is not the {v} build")
    text = sheet(v)
    bad = stale_words(text)
    if bad:
        raise SystemExit(f"the sheet names {bad}, which went stale; fix the rows")
    top = f"cartogen_ai_hand_test_v2_{v}"
    out_dir = Path(sys.argv[sys.argv.index("--out-dir") + 1]).resolve() if "--out-dir" in sys.argv else REPO / "dist"          # tests build into a temp folder
    out = out_dir / f"{top}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(plugin_zip.read_bytes()).hexdigest()
    results = "id,row,prompt,result (Pass/Partial/Fail/Skip),notes\n" + "".join(
        f"{r['id']},{r['issue']},\"{fill(r['title'], v)}\",,\n" for r in rows())
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{top}/README_FIRST.txt", readme(v, len(rows())).replace("\n", "\r\n"))
        z.write(plugin_zip, f"{top}/1_plugin/{plugin_zip.name}")
        z.writestr(f"{top}/1_plugin/checksum_sha256.txt", f"{digest}  {plugin_zip.name}\n")
        z.write(REPO / "tools" / "layout_check_script.py", f"{top}/2_layout_check/layout_check_script.py")
        for tool in TOOLS_FOLDER:
            z.write(REPO / "tools" / tool, f"{top}/6_tools/{tool}")
        z.writestr(f"{top}/3_SHEET.md", text)
        z.writestr(f"{top}/4_RESULTS.csv", results)
        z.write(REPO / "docs" / "HAND_TEST_PACKAGE_1.18.5.md", f"{top}/0_GUIDE.md")
        z.write(REPO / "docs" / "WORKFLOW_FILES.md", f"{top}/3_test_files/WORKFLOW_FILES.md")
        z.writestr(f"{top}/EVIDENCE_HOWTO.txt", EVIDENCE_PAGE.replace("\n", "\r\n"))
        for row in rows():
            z.writestr(f"{top}/results/evidence/{row['id']}/CHECKLIST.txt", checklist(row, v))
            z.writestr(f"{top}/results/outputs/{row['id']}/PUT_OUTPUT_FILES_HERE.txt", f"Files row {row['id']} makes go here (see ../../evidence/{row['id']}/CHECKLIST.txt).\r\n")
        z.writestr(f"{top}/results/screens/PUT_SCREENSHOTS_HERE.txt", "Screenshots a row asks for, named as the row says.\r\n")
        z.writestr(f"{top}/results/logs/WRITTEN_BY_SNAP.txt", "snap() writes one CartogenAI log per row here.\r\n")
        z.writestr(f"{top}/results/README.txt", "Everything the run produces goes here: evidence/, outputs/, screens/, logs/. How: see ../EVIDENCE_HOWTO.txt.\r\n")
        z.write(REPO / "tools" / "check_evidence.py", f"{top}/5_check_evidence.py")
        z.write(ROWS_FILE, f"{top}/3_ROWS.json")
        needed = set(re.findall(FIXTURE_NAME, text)) | set(PROJECT_FILES) | {name for row in rows() for name in row.get("files", [])}
        for name in sorted(needed):
            source = next((folder / name for folder in (INPUTS, EXTRA_INPUTS) if (folder / name).is_file()), None)
            if source is None:
                raise SystemExit(f"a row names {name}, which is in neither fixture folder")
            z.write(source, f"{top}/3_test_files/{name}")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
