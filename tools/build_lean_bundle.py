#!/usr/bin/env python3
"""Builds the LEAN hand-test bundle: only what changed since the last tested release, not the whole sheet.

    python tools/build_lean_bundle.py --plugin-zip dist/cartogen_ai_v1.17.0-rc47.zip   # writes dist/cartogen_ai_lean_test_<version>.zip

Rows (see docs/LEAN_HAND_TEST_PROTOCOL.md): the tool rows a fix this release targeted, a few canaries, the Part 4 prompts whose cause is
still unconfirmed, and a sample of the plain-language prompts (the ones the offline check could not place in the first 15 matches, plus a
few that it could, so a wrong offline number shows). Standard library only; the bundle holds no credentials and no .py files."""
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
)
PLAIN_FOUND, PLAIN_SAMPLE_SEED = 6, 47


def version():
    return re.search(r"^version=(\S+)", (REPO / "metadata.txt").read_text(encoding="utf-8"), re.M).group(1)


def read_csv(name):
    with open(DOCS / name, encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


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

    sheet = [f"# Cartogen AI {v} - lean hand test\n",
             "Run on a **fresh QGIS project** with the fixtures from `3_fixtures_script.txt`. **One new chat per row** (history makes every later row dearer). "
             "Screenshots only for rows that fail or look wrong. Do not repeat rows that are not here: their code did not change.\n",
             "Scoring per row: Pass / Partial / Fail / Skip. Note (1) did the assistant choose the right tool without being told its name, (2) does the result look right.\n",
             "Prerequisite for the layout rows: the request `create a print layout of the map called Test Layout`.\n",
             f"## A. Changed or fix-targeted rows ({len(tool_rows)})\n", "| # | Row | Prompt | Expect |", "|---|---|---|---|"]
    sheet += [f"| A{i} | `{t}` | {p} | {e} |" for i, (t, p, e) in enumerate(tool_rows, 1)]
    sheet += [f"\n## B. Plain-language sample ({len(plain_rows)})\n",
              "The prompt never names the algorithm. Pass = the assistant found and ran an algorithm that does the job (write which one in the notes).\n",
              "| # | Algorithm that fits | Prompt |", "|---|---|---|"]
    sheet += [f"| B{i} | `{a}` | {p} |" for i, (a, p, _) in enumerate(plain_rows, 1)]
    sheet_text = "\n".join(sheet) + "\n"

    results = [("id", "row", "prompt", "result (Pass/Partial/Fail/Skip)", "notes")]
    results += [(f"A{i}", t, p, "", "") for i, (t, p, _) in enumerate(tool_rows, 1)]
    results += [(f"B{i}", a, p, "", "") for i, (a, p, _) in enumerate(plain_rows, 1)]

    fixtures_sheet = (DOCS / "HAND_TEST_SHEET_rc44_2026-10-16.md").read_text(encoding="utf-8")
    fixture = re.search(r"```python\n(.*?)```", fixtures_sheet, re.S)
    if not fixture:
        raise SystemExit("the full sheet has no fixture script block")
    digest = hashlib.sha256(plugin_zip.read_bytes()).hexdigest()
    top = f"cartogen_ai_lean_test_{v}"
    out = REPO / "dist" / f"{top}.zip"
    out.parent.mkdir(exist_ok=True)
    readme = (f"Cartogen AI {v} - LEAN hand test ({len(tool_rows)} + {len(plain_rows)} rows)\r\n"
              "====================================================\r\n\r\n"
              "1_plugin/ the plugin zip (SHA-256 in checksum_sha256.txt)\r\n2_LEAN_SHEET.md START HERE\r\n3_fixtures_script.txt PyQGIS script for the test layers\r\n"
              "4_RESULTS.csv fill result + notes\r\n\r\n"
              "Keep the cost down: new chat per row; screenshots only for failures; after the run save Log Messages (CartogenAI tab) as cartogen.log and send it.\r\n"
              "It is turned into a cost table with: python tools/summarize_usage_log.py cartogen.log\r\n")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{top}/README_FIRST.txt", readme)
        z.write(plugin_zip, f"{top}/1_plugin/{plugin_zip.name}")
        z.writestr(f"{top}/1_plugin/checksum_sha256.txt", f"{digest}  {plugin_zip.name}\n")
        z.writestr(f"{top}/2_LEAN_SHEET.md", sheet_text)
        z.writestr(f"{top}/3_fixtures_script.txt", fixture.group(1))
        import io
        buffer = io.StringIO()
        csv.writer(buffer).writerows(results)
        z.writestr(f"{top}/4_RESULTS.csv", "﻿" + buffer.getvalue())
        z.writestr(f"{top}/screenshots/PUT_FILES_HERE.txt", "Only for failing or odd rows, named with the row id.\r\n")
    with zipfile.ZipFile(out) as z:
        if [n for n in z.namelist() if n.endswith(".py")]:
            raise SystemExit("the bundle must not contain .py files")
    print(f"wrote {out} ({out.stat().st_size} bytes); A rows {len(tool_rows)}, B rows {len(plain_rows)}; plugin sha256 {digest}")


if __name__ == "__main__":
    main()
