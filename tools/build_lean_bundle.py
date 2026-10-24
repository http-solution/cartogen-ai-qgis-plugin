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

# rc49: the tools the rc48 hand test found failing or partial and PLAN-008 to PLAN-012 changed (rows come from the rc44 tool sheet when it has one).
TARGET_TOOLS = ("print_map", "add_layout_chart", "add_layout_elevation_profile", "tidy_project_layers", "classify_facilities_by_access",
                "generate_html_dashboard", "export_layout")
CANARY_TOOLS = ("set_layer_elevation",)
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
    # Failed or Partial in the rc48 hand test and fixed or re-specified since (PLAN-008): run again.
    ("E2c pdf", "send me the map as a pdf",
     "export_layout is used on Test Layout (create it first with the prerequisite request); a PDF exists at the reported path and opens."),
    ("E2c package", "bundle the project data for sharing",
     "package_layers_offline is used; a GeoPackage with the project layers exists at the reported path."),
    ("E2c dxf", "export the roads and towns to dxf",
     "export_layers_to_dxf; the DXF opens (in QGIS or a CAD program) and shows the lines and points; the reply says it carries geometry and layer names only. (Sending the same request again over the unchanged file does not ask: that is a re-run by design. To see the replace card, change or replace the file outside QGIS first.)"),
    ("E2c excel", "export the towns and districts to excel, one sheet each",
     "export_layers_to_spreadsheet; the .xlsx opens in Excel or LibreOffice with two sheets whose row counts match the layers as they are now (fresh fixtures: towns 8, districts 4) and the right columns."),
    # rc49 (PLAN-008 to PLAN-012): none of these has been run outside CI. Rows for the open issues OI-120, OI-128, OI-145/146, OI-148 and OI-150
    # are NOT repeated here: the open-issue part of the bundle carries them for as long as those issues are open.
    ("P8 routing", "sort the districts by population, biggest first",
     "The assistant runs a sort/order algorithm (native:orderbyexpression or similar) on districts; it does NOT start a 'Map population distribution' mapping task."),
    ("P8 geometry", "convert the districts lines to polygons with qgis:linestopolygons",
     "The districts layer already holds polygons, so the assistant says that algorithm needs a line layer and stops (or picks another way) in a few calls; no raw TypeError and no 20-call loop."),
    ("P10 coverage", "make a sector coverage report from these rows: Health reached 900 target 1000; WASH reached 150 target 0; Shelter reached 400 target 800",
     "generate_sector_coverage_report; the table shows Health 90.0 and Shelter 50.0 percent, WASH with no coverage figure; the chart has bars for Health and Shelter only and the reply says WASH has no usable target (it is not a zero bar)."),
    ("P12 multipoint", "blur the sens_multi points by 100 metres",
     "obfuscate_sensitive_points with jitter radius 100; a layer sens_multi_obfuscated with 3 points (one per part), each within 100 m of an original, none at the map origin; no error."),
    ("P12 contours", "draw contour lines of the dem every 100",
     "create_contours (or gdal:contour); the reply gives the file path and, when it is in the system temporary folder, says so."),
    ("P11 gate", "tag the towns layer as SENSITIVE (reason: test), then export Test Layout to a pdf",
     "A confirm card names towns (SENSITIVE) and nothing is written yet; pressing Apply writes the PDF and the reply mentions the protected layer. (Create Test Layout first with the prerequisite request.)"),
    ("P11 publication", "export Test Layout as a publication pdf for sharing outside the team",
     "The assistant lists the problems (protected layer, any missing element) and ASKS YOU for a reason; it does not invent one. After you give a reason you get a card that shows it; after Apply, a file named <pdf>.publication.json beside the PDF holds your reason."),
    ("P11 atlas", "export one pdf per district from Test Layout using the name field",
     "With the districts layer tagged SENSITIVE a card appears first; after Apply one PDF per district is written; untagged, no card."),
    ("P11 footer", "create a print layout called Footer Test",
     "The page footer shows the AI note, a Sources line with each visible layer (organisation and date if the layer has metadata, otherwise the file name), and a boundary and data-sensitivity sentence. Nothing overlaps at the bottom of the page. Look at the exported page, not only the reply. In Settings the 'Layout disclaimer' checkbox and 'Disclaimer wording' box exist; with your own wording typed, a NEW layout shows it."),
)
# Added to the fixture script: a small integer raster for the polygonize row (kept from rc48) and a MultiPoint layer for the rc49 obfuscation row.
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

# rc49: a MultiPoint layer for the obfuscation row (EPSG:32638, metres)
_mp = QgsVectorLayer("MultiPoint?crs=EPSG:32638&field=id:integer", "sens_multi", "memory")
for _wkt, _id in (("MULTIPOINT((500000 1650000),(500400 1650300))", 1), ("MULTIPOINT((501000 1651000))", 2)):
    _f = QgsFeature(_mp.fields()); _f.setGeometry(QgsGeometry.fromWkt(_wkt)); _f.setAttributes([_id]); _mp.dataProvider().addFeatures([_f])
_mp.updateExtents()
QgsProject.instance().addMapLayer(_mp)
print("sens_multi added")
"""
PLAIN_FOUND, PLAIN_SAMPLE_SEED = 6, 47
# Plain-language rows that Failed in the rc48 hand test and were addressed since (B7, B15, B28, B32, B41; B3 has its own row above): always included.
FORCE_PLAIN = ("grass:r.circle", "grass:r.sunmask.datetime", "grass:v.patch", "grass:v.to.rast", "native:meshrasterize")
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
    have = {r["algorithm_id"] for r in (*missed, *picks[:PLAIN_FOUND])}
    forced = [r for r in rows if r["algorithm_id"] in FORCE_PLAIN and r["algorithm_id"] not in have]
    return missed, picks[:PLAIN_FOUND] + forced


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
