#!/usr/bin/env python3
"""Builds the hand-test bundle for the current version: the plugin zip, the hand-test sheet for everything new in 1.17, the two results
spreadsheets, and the PyQGIS fixture script as plain text. A tester needs no Python outside QGIS.

    python tools/build_hand_test_bundle.py --plugin-zip dist/cartogen_ai_v1.17.0-rc46.zip   # writes dist/cartogen_ai_hand_test_<version>.zip

The plugin zip is passed in (built with plugin_upload.py from the release commit) so the bundle and the directory upload carry one checksum.
Standard library only. The bundle holds only synthetic data instructions and public documents; it never includes credentials, traces or results."""
import hashlib
import re
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"
SHEET = DOCS / "HAND_TEST_SHEET_rc44_2026-10-16.md"
PLAIN_SHEET = DOCS / "HAND_TEST_SHEET_plain_language_2026-10-17.md"
CSVS = (("HAND_TEST_rc44_tools.csv", "3_RESULTS_tools.csv"), ("HAND_TEST_rc44_algorithms.csv", "4_RESULTS_algorithms.csv"),
        ("HAND_TEST_rc46_algorithms_plain.csv", "6_PLAIN_LANGUAGE_algorithms.csv"))


def version():
    return re.search(r"^version=(\S+)", (REPO / "metadata.txt").read_text(encoding="utf-8"), re.M).group(1)


def fixture_script(sheet_text):
    found = re.search(r"```python\n(.*?)```", sheet_text, re.S)
    if not found:
        raise SystemExit("the hand-test sheet has no fixture script block")
    return found.group(1)


def main():
    if "--plugin-zip" not in sys.argv:
        raise SystemExit("usage: build_hand_test_bundle.py --plugin-zip FILE.zip")
    plugin_zip = Path(sys.argv[sys.argv.index("--plugin-zip") + 1]).resolve()
    if not plugin_zip.is_file():
        raise SystemExit(f"plugin zip not found: {plugin_zip}")
    v = version()
    if f"_v{v}.zip" not in plugin_zip.name:
        raise SystemExit(f"{plugin_zip.name} is not the {v} build")
    top = f"cartogen_ai_hand_test_{v}"
    out = REPO / "dist" / f"{top}.zip"
    out.parent.mkdir(exist_ok=True)
    sheet = SHEET.read_text(encoding="utf-8")
    digest = hashlib.sha256(plugin_zip.read_bytes()).hexdigest()
    readme = (
        f"Cartogen AI {v} - hand test of the new functionality\r\n"
        "=========================================================\r\n\r\n"
        "What this is: a test of everything added in 1.17 (rc42 to rc46; run on rc46) that nobody has tried by hand: 82 tools and 385 Processing\r\n"
        "algorithms. It is NOT an installation or update test.\r\n\r\n"
        "Files\r\n"
        f"  1_plugin/cartogen_ai_v{v}.zip      the plugin (QGIS: Plugins > Manage and Install > Install from ZIP). SHA-256 in checksum_sha256.txt\r\n"
        "  2_HAND_TEST_SHEET.md               START HERE: fixtures, scoring rules, every tool and integration check, algorithm priority list\r\n"
        "  3_RESULTS_tools.csv                one row per tool (83) - fill the Result and Notes columns\r\n"
        "  4_RESULTS_algorithms.csv           one row per algorithm (385) with a ready-to-paste prompt - fill Result and Notes\r\n"
        "  6_PLAIN_LANGUAGE_algorithms.csv    the same 385 algorithms asked in plain humanitarian wording, never naming the algorithm. Read\r\n"
        "                                     7_PLAIN_LANGUAGE_SHEET.md first. This is the test of whether the assistant FINDS an algorithm from a description\r\n"
        "  5_fixtures_script.txt              PyQGIS script that builds the test layers (paste into the QGIS Python console). Untested: if it errors, make\r\n"
        "                                     layers with the same names by hand (towns, roads, districts, dem, dem2, mesh1)\r\n"
        "  screenshots/ evidence/ logs/ outputs/   put proof of anything that fails or looks wrong here, named with the row\r\n\r\n"
        "Two things CI cannot check, so note them on every row: (1) did the model pick the right tool without being told its name?\r\n"
        "(2) does the result LOOK right?\r\n\r\n"
        "Nothing in 1.17 has been hand-tested before this. Send back the two CSVs plus the folders above.\r\n")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{top}/README_FIRST.txt", readme)
        z.write(plugin_zip, f"{top}/1_plugin/{plugin_zip.name}")
        z.writestr(f"{top}/1_plugin/checksum_sha256.txt", f"{digest}  {plugin_zip.name}\n")
        z.writestr(f"{top}/2_HAND_TEST_SHEET.md", sheet)
        for src, dst in CSVS:
            z.write(DOCS / src, f"{top}/{dst}")
        z.writestr(f"{top}/5_fixtures_script.txt", fixture_script(sheet))
        z.writestr(f"{top}/7_PLAIN_LANGUAGE_SHEET.md", PLAIN_SHEET.read_text(encoding="utf-8"))
        for folder, note in (("screenshots", "Save one screenshot per failing or odd row, named with the tool or algorithm id."),
                             ("evidence", "Copy any cartogen_evidence folder from next to your saved project here."),
                             ("logs", "Save the Log Messages text (CartogenAI tab) as log_<row>.txt, and the QGIS About text as qgis_about.txt."),
                             ("outputs", "Copy files the assistant created (PDF, PNG, GeoPackage, QLR...) here, named with the row.")):
            z.writestr(f"{top}/{folder}/PUT_FILES_HERE.txt", note + "\r\n")
    with zipfile.ZipFile(out) as z:
        scripts = [n for n in z.namelist() if n.endswith(".py")]
    if scripts:
        raise SystemExit("the bundle must not contain .py files: " + ", ".join(scripts))
    print(f"wrote {out} ({out.stat().st_size} bytes); plugin sha256 {digest}")


if __name__ == "__main__":
    main()
