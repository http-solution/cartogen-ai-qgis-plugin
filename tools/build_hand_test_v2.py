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
INPUTS = REPO / "docs" / "release_smoke_assets" / "inputs"
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
            "3_SHEET.md           the rows that still need you\n"
            "3_test_files/        input data some rows use\n"
            "4_RESULTS.csv        fill in the result and notes\n"
            "5_check_evidence.py  not for you: it reads what you send back\n\n"
            "STEP A - the layout check (about two minutes, no API cost)\n"
            "  Install the plugin (see below), open QGIS, open the Python console (Plugins > Python Console), then type:\n"
            '     exec(open(r"<path to this folder>\\2_layout_check\\layout_check_script.py", encoding="utf-8").read())\n'
            "  It builds its own project, makes about a dozen layouts and exports them. When it finishes it prints PASS or FAIL for each check and\n"
            "  the folder it wrote (also in your temp folder). Send that whole folder back.\n\n"
            "STEP B - the rows in 3_SHEET.md (each starts from the state it names; none depends on another)\n"
            "  Tick 'Save an evidence folder for each request' in the Cartogen Settings first, and send the cartogen_evidence folder back.\n\n"
            "Send back: the layout_check folder, 4_RESULTS.csv, the cartogen_evidence folder, and any screenshots the rows ask for.\n\n"
            + fill(UPDATE_STEPS, v))


def sheet(v):
    out = [f"# Cartogen AI {v} - hand test v2\n",
           ("Only what needs a person, a real model or your computer's fonts. The layout script (STEP A in README_FIRST.txt) covers footer, legend, "
            "page sizes, names, presets, profile, logo and sign-off by measurement and exports the pages for you to look at.\n")]
    for row in rows():
        out += [f"### {row['id']} ({row['issue']}): {fill(row['title'], v)}", "",
                f"- **Starts from:** {fill(row['starts_from'], v)}", f"- **Do:** {fill(row['do'], v)}",
                f"- **Expect:** {fill(row['expect'], v)}", f"- **Save:** {fill(row['evidence'], v)}", f"- **Needs:** {row['needs']}", ""]
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
    out = REPO / "dist" / f"{top}.zip"
    out.parent.mkdir(exist_ok=True)
    digest = hashlib.sha256(plugin_zip.read_bytes()).hexdigest()
    results = "id,row,prompt,result (Pass/Partial/Fail/Skip),notes\n" + "".join(
        f"{r['id']},{r['issue']},\"{fill(r['title'], v)}\",,\n" for r in rows())
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{top}/README_FIRST.txt", readme(v, len(rows())).replace("\n", "\r\n"))
        z.write(plugin_zip, f"{top}/1_plugin/{plugin_zip.name}")
        z.writestr(f"{top}/1_plugin/checksum_sha256.txt", f"{digest}  {plugin_zip.name}\n")
        z.write(REPO / "tools" / "layout_check_script.py", f"{top}/2_layout_check/layout_check_script.py")
        z.writestr(f"{top}/3_SHEET.md", text)
        z.writestr(f"{top}/4_RESULTS.csv", results)
        z.write(REPO / "tools" / "check_evidence.py", f"{top}/5_check_evidence.py")
        needed = set(re.findall(r"smoke_[A-Za-z_]+\.[a-z]+", text))
        for name in sorted(needed):
            if (INPUTS / name).is_file():
                z.write(INPUTS / name, f"{top}/3_test_files/{name}")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
