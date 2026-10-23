#!/usr/bin/env python3
"""Builds the ONE hand-test bundle for a release: only what is not already proven, not the whole sheet.

    python tools/build_lean_bundle.py --plugin-zip dist/cartogen_ai_v1.17.0-rc47.zip   # writes dist/cartogen_ai_test_bundle_<version>.zip

Part 1, open issues: the rows of docs/FULL_LIVE_TEST_open_issues_ROWS.csv whose issue is still open according to the table in
docs/OPEN_ISSUES_STATUS_<date>.md (the single source of truth for what is open). Rows whose issues were closed with evidence are left out.
Part 2, this release (see docs/LEAN_HAND_TEST_PROTOCOL.md): the tool rows a fix targeted, a few canaries, the Part 4 prompts whose cause is
unconfirmed, and a sample of plain-language prompts (the ones the offline check could not place in the first 15 matches, plus a few it could,
so a wrong offline number shows). Standard library only; the bundle holds no credentials and no .py files."""
import csv
import hashlib
import random
import re
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"
sys.path.insert(0, str(REPO / "src"))

TARGET_TOOLS = ("set_project_crs", "assign_layer_crs", "go_to_bookmark", "get_layer_metadata", "raster_calculator", "add_layout_elevation_profile",
                "apply_saved_symbol", "merge_features", "split_features_by_line", "delete_features", "rename_layer_group")
CANARY_TOOLS = ("add_layout_chart", "set_layer_elevation")
EXTRA_ROWS = (
    ("tidy_project_layers", "Add the vector tile layer https://basemaps.cartocdn.com/vectortiles/carto.streets/v1/{z}/{x}/{y}.mvt, then tidy the project layers (preview only, do not apply).",
     "A tidy preview is shown; no error about featureCount."),
    ("I4 animate", "animate the layer over time",
     "The assistant calls export_temporal_animation_frames, or asks which layer/time field to use. A how-to explanation is a Fail."),
    ("I6 profile", "Turn on elevation for the dem, then draw an elevation profile along the road in Test Layout",
     "set_layer_elevation then add_layout_elevation_profile with along_layer roads, in 4 model calls or fewer; no repeated list_layout_items."),
    ("I9 chart", "Produce charts linked to maps",
     "add_layout_chart and/or the atlas tools are used on a layout. An HTML dashboard instead is a Fail."),
    ("I10 undo", "undo the last operation", "The last change is undone (one confirm card); no second stale card."),
    # rc48 (wave E1 of PLAN-005 and package E2c of PLAN-006): none of these has been run outside CI.
    ("E1 raster stats", "what are the minimum, maximum and mean elevation of the dem",
     "The generic Processing tool runs native:rasterlayerstatistics and the reply gives minimum, maximum and mean numbers that look right for the dem; no file path is asked for."),
    ("E1 field stats", "give me the basic statistics of the pop field of towns",
     "native:basicstatisticsforfields; the reply says minimum 5, maximum 700, mean about 190.6 (8 towns); no file path is asked for."),
    ("E1 polygonize", "turn the dem_classes raster into editable polygons",
     "gdal:polygonize; a polygon layer appears in the project, is marked temporary with an offer to save it; the polygon values are 1, 2 and 3."),
    ("E2c pdf", "send me the map as a pdf",
     "export_layout is used on Test Layout (create it first with the prerequisite request); a PDF exists at the reported path and opens."),
    ("E2c package", "bundle the project data for sharing",
     "package_layers_offline is used; a GeoPackage with the project layers exists at the reported path."),
    ("E2c geopackage", "save the roads layer to a geopackage",
     "export_layer with format gpkg; the file is in the project export folder and holds 3 road features."),
    ("E2c dxf", "export the roads and towns to dxf",
     "export_layers_to_dxf; the DXF opens (in QGIS or a CAD program) and shows the lines and points; the reply says it carries geometry and layer names only. Send the same request again: the second run must ask before replacing the file."),
    ("E2c excel", "export the towns and districts to excel, one sheet each",
     "export_layers_to_spreadsheet; the .xlsx opens in Excel or LibreOffice with two sheets (towns 8 rows, districts 4 rows) and the right columns."),
)
# Added to the fixture script: a small integer raster for the polygonize row (the dem is continuous, so its polygons would be one per pixel).
FIXTURE_EXTRA = """
# rc48: classified raster for the polygonize row
_classes_path = os.path.join(folder, "dem_classes.tif")
_ds = gdal.GetDriverByName("GTiff").Create(_classes_path, 80, 80, 1, gdal.GDT_Int16)
_ds.SetGeoTransform((0.0, 0.05, 0.0, 4.0, 0.0, -0.05))
_srs = osr.SpatialReference(); _srs.ImportFromEPSG(4326); _ds.SetProjection(_srs.ExportToWkt())
_y, _x = np.mgrid[0:80, 0:80]
_ds.GetRasterBand(1).WriteArray((1 + (_x // 27)).astype("int16")); _ds.FlushCache(); _ds = None
QgsProject.instance().addMapLayer(QgsRasterLayer(_classes_path, "dem_classes"))
print("dem_classes added")
"""
PLAIN_FOUND, PLAIN_SAMPLE_SEED = 6, 47
SETUP_ROWS = ("OI-S1", "OI-S2")          # the open-issue rows need these layers loaded and renamed first
UMBRELLA_ROWS = ("OI-233",)              # tracking lists, not tests
INPUTS = DOCS / "release_smoke_assets" / "inputs"


def version():
    return re.search(r"^version=(\S+)", (REPO / "metadata.txt").read_text(encoding="utf-8"), re.M).group(1)


def read_csv(name):
    with open(DOCS / name, encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def open_issue_numbers():
    """Issue numbers still open, read from the first column of the newest docs/OPEN_ISSUES_STATUS_*.md table."""
    latest = sorted(DOCS.glob("OPEN_ISSUES_STATUS_20*.md"))[-1]
    numbers = set()
    for line in latest.read_text(encoding="utf-8").splitlines():
        cell = line.split("|")[1].strip() if line.startswith("|") and line.count("|") > 3 else ""
        if cell and re.fullmatch(r"\d+(, \d+)*|\d+/\d+", cell):
            numbers.update(int(n) for n in re.findall(r"\d+", cell))
    return numbers


def open_issue_rows():
    """Rows of the open-issue sheet that test an issue that is still open, plus the set-up rows they depend on."""
    open_numbers = open_issue_numbers()
    chosen = []
    for row in read_csv("FULL_LIVE_TEST_open_issues_ROWS.csv"):
        if row["id"] in UMBRELLA_ROWS:
            continue
        cited = {int(n) for n in re.findall(r"#(\d+)", row["source"].split("(")[0])}
        if row["id"] in SETUP_ROWS or cited & open_numbers:
            chosen.append(row)
    return chosen


def plain_sample():
    """Offline misses (algorithm not in the first 15 matches) plus PLAIN_FOUND found ones, one family spread, fixed seed."""
    from cartogen_ai.core.agent import algorithm_topics as at
    rows = read_csv("HAND_TEST_rc46_algorithms_plain.csv")
    missed, found = [], []
    for row in rows:
        ids = [hit[0] if isinstance(hit, (tuple, list)) else hit for hit in at.rank(row["plain_prompt"])][:15]
        (found if row["algorithm_id"] in ids else missed).append(row)
    rng = random.Random(PLAIN_SAMPLE_SEED)  # noqa: S311 -- a reproducible test sample, not security
    by_family = {}
    for row in found:
        by_family.setdefault(row["family"], []).append(row)
    picks = [rng.choice(group) for _, group in sorted(by_family.items())]
    rng.shuffle(picks)
    return missed, picks[:PLAIN_FOUND]


def main():
    if "--plugin-zip" not in sys.argv:
        raise SystemExit("usage: build_lean_bundle.py --plugin-zip FILE.zip")
    plugin_zip = Path(sys.argv[sys.argv.index("--plugin-zip") + 1]).resolve()
    if not plugin_zip.is_file():
        raise SystemExit(f"plugin zip not found: {plugin_zip}")
    v = version()
    if f"_v{v}.zip" not in plugin_zip.name:
        raise SystemExit(f"{plugin_zip.name} is not the {v} build")
    tools = {row["tool"].split(" ")[0]: row for row in read_csv("HAND_TEST_rc44_tools.csv")}
    tool_rows = [(t, tools[t]["prompt"], tools[t]["expected"]) for t in (*TARGET_TOOLS, *CANARY_TOOLS) if t in tools] + list(EXTRA_ROWS)
    missed, found = plain_sample()
    plain_rows = [(r["algorithm_id"], r["plain_prompt"], r["expected"]) for r in (*missed, *found)]
    oi_rows = open_issue_rows()

    sheet = [f"# Cartogen AI {v} - hand test (open issues + this release)\n",
             ("One new chat per row (history makes every later row dearer). Screenshots only for rows that fail or look wrong. "
              "Rows already proven are not here. Scoring: Pass / Partial / Fail / Skip; note which tool the assistant chose and whether the result looks right.\n"),
             "**Order:** Part 1 first in the project made by its two set-up rows; then start a NEW project, run `3_fixtures_script.txt` in the QGIS Python console, and do Part 2.\n",
             f"## Part 1. Open issues ({len(oi_rows)} rows, input files in `2_test_files/`)\n"]
    for row in oi_rows:
        sheet += [f"### {row['id']} ({row['source']})", "",
                  f"- **Do/Send:** {row['prompt_or_action']}", f"- **Expect:** {row['expected']}",
                  f"- **Inputs:** {row['inputs_used'] or 'none'}", f"- **Last known:** {row['last_known']}",
                  f"- **Save:** {row['evidence_to_save']}", ""]
    sheet += ["Prerequisite for the layout rows of Part 2: the request `create a print layout of the map called Test Layout`.\n",
              f"## Part 2. This release ({len(tool_rows)} tool rows + {len(plain_rows)} plain-language rows)\n",
              f"### A. Changed or fix-targeted rows ({len(tool_rows)})\n", "| # | Row | Prompt | Expect |", "|---|---|---|---|"]
    sheet += [f"| A{i} | `{t}` | {p} | {e} |" for i, (t, p, e) in enumerate(tool_rows, 1)]
    sheet += [f"\n### B. Plain-language sample ({len(plain_rows)})\n",
              "The prompt never names the algorithm. Pass = the assistant found and ran an algorithm that does the job (write which one in the notes).\n",
              "| # | Algorithm that fits | Prompt |", "|---|---|---|"]
    sheet += [f"| B{i} | `{a}` | {p} |" for i, (a, p, _) in enumerate(plain_rows, 1)]
    sheet_text = "\n".join(sheet) + "\n"

    results = [("id", "row", "prompt", "result (Pass/Partial/Fail/Skip)", "tool/algorithm the assistant chose", "model calls", "notes")]
    results += [(r["id"], r["source"], r["prompt_or_action"], "", "", "", "") for r in oi_rows]
    results += [(f"A{i}", t, p, "", "", "", "") for i, (t, p, _) in enumerate(tool_rows, 1)]
    results += [(f"B{i}", a, p, "", "", "", "") for i, (a, p, _) in enumerate(plain_rows, 1)]

    fixtures_sheet = (DOCS / "HAND_TEST_SHEET_rc44_2026-10-16.md").read_text(encoding="utf-8")
    fixture = re.search(r"```python\n(.*?)```", fixtures_sheet, re.S)
    if not fixture:
        raise SystemExit("the full sheet has no fixture script block")
    digest = hashlib.sha256(plugin_zip.read_bytes()).hexdigest()
    top = f"cartogen_ai_test_bundle_{v}"
    out = REPO / "dist" / f"{top}.zip"
    out.parent.mkdir(exist_ok=True)
    total = len(oi_rows) + len(tool_rows) + len(plain_rows)
    readme = (f"Cartogen AI {v} - hand test bundle ({total} rows: {len(oi_rows)} open-issue, {len(tool_rows)} release, {len(plain_rows)} plain-language)\r\n"
              "=====================================================================\r\n\r\n"
              "1_plugin/ the plugin zip (SHA-256 in checksum_sha256.txt)\r\n2_SHEET.md START HERE\r\n2_test_files/ input data for Part 1\r\n"
              "3_fixtures_script.txt PyQGIS script for the layers of Part 2\r\n4_RESULTS.csv fill result + the tool the assistant chose + notes\r\n\r\n"
              "Keep the cost down: new chat per row; screenshots only for failures; after the run save Log Messages (CartogenAI tab) as cartogen.log and send it.\r\n"
              "It is turned into a cost table with: python tools/summarize_usage_log.py cartogen.log\r\n")
    inputs = [p for p in sorted(INPUTS.iterdir()) if p.is_file()]
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{top}/README_FIRST.txt", readme)
        z.write(plugin_zip, f"{top}/1_plugin/{plugin_zip.name}")
        z.writestr(f"{top}/1_plugin/checksum_sha256.txt", f"{digest}  {plugin_zip.name}\n")
        z.writestr(f"{top}/2_SHEET.md", sheet_text)
        for path in inputs:
            z.write(path, f"{top}/2_test_files/{path.name}")
        z.writestr(f"{top}/3_fixtures_script.txt", fixture.group(1) + FIXTURE_EXTRA)
        import io
        buffer = io.StringIO()
        csv.writer(buffer).writerows(results)
        z.writestr(f"{top}/4_RESULTS.csv", "﻿" + buffer.getvalue())
        z.writestr(f"{top}/screenshots/PUT_FILES_HERE.txt", "Only for failing or odd rows, named with the row id.\r\n")
    with zipfile.ZipFile(out) as z:
        if [n for n in z.namelist() if n.endswith(".py")]:
            raise SystemExit("the bundle must not contain .py files")
    print(f"wrote {out} ({out.stat().st_size} bytes); open-issue rows {len(oi_rows)}, A rows {len(tool_rows)}, B rows {len(plain_rows)}; plugin sha256 {digest}")


if __name__ == "__main__":
    main()
