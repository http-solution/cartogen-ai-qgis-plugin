#!/usr/bin/env python3
"""Builds docs/qgis_coverage/actions_matrix.csv (and, given a registry dump, processing_matrix.csv) from tools/qgis_coverage_actions.py.

    python tools/build_qgis_coverage.py                      # actions matrix + printed summary
    python tools/build_qgis_coverage.py --registry LOG.txt   # also the Processing matrix, from the CI registry dump

Status of an action row: COVERED (a named tool exists and the real router offers it for the phrase), PARTIAL (a tool exists and is offered, but
the note names what it does not do), ROUTING-GAP (a tool exists, the router does not offer it for the phrase), MISSING (no tool),
BLOCKED (left out on purpose, the note says why). Nothing here calls QGIS; it needs only the package on sys.path."""
import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tools"))

import qgis_coverage_actions as catalogue  # noqa: E402
from cartogen_ai.core.agent.tools import TOOLS_SCHEMA  # noqa: E402
from cartogen_ai.core.services.tool_router import ToolRouter  # noqa: E402

OUT = REPO / "docs" / "qgis_coverage"


def action_status(router, registered):
    out = []
    for area, action, ref, phrase, tools, prio, note in catalogue.ROWS:
        if isinstance(tools, str):
            status, offered = "BLOCKED", ""
            tool_text = tools
        elif tools is None:
            status, offered, tool_text = "MISSING", "", ""
        else:
            unknown = [t for t in tools if t not in registered]
            if unknown:
                raise SystemExit(f"row {action!r} names unknown tool(s): {unknown}")
            names = {t["function"]["name"] for t in router.filter_relevant_tools(phrase)}
            hit = [t for t in tools if t in names]
            offered = ", ".join(hit)
            tool_text = ", ".join(tools)
            if not hit:
                status = "ROUTING-GAP"
            elif note.startswith("PARTIAL"):
                status = "PARTIAL"
            else:
                status = "COVERED"
        out.append({"area": area, "action": action, "priority": prio, "status": status, "tools": tool_text, "offered_for_phrase": offered,
                    "phrase": phrase, "note": note, "doc_reference": ref})
    return out


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


SECURITY_RISK_FLAG = 32768          # Qgis.ProcessingAlgorithmFlag.SecurityRisk: set on exactly one algorithm in the 4.2.2 image (the Python field calculator)
FILE_OUTPUT_TYPES = {"fileDestination", "folderDestination", "vectorDestination", "pointCloudDestination", "vectorTileDestination", "meshDestination"}
PATH_INPUT_TYPES = {"file", "folder", "authcfg", "connection", "databaseschema", "databasetable", "layout", "layoutitem", "providerconnection"}
SPECIAL_LAYER_TYPES = {"pointcloud", "mesh", "tiledscene", "vectortilelayer", "annotation", "pointcloudlayer", "meshlayer"}
CODE_PARAM_NAMES = re.compile(r"^(FORMULA|CODE|SCRIPT|GLOBAL|SQL|QUERY|COMMAND|ARGUMENTS?)$", re.I)
RAW_ARGUMENT_PARAM_NAMES = re.compile(r"^(EXTRA|OPTIONS|CREATION_OPTIONS)$", re.I)


def classify_algorithm(a, in_allowlist):
    """One disposition per algorithm, from the real parameter definitions and QGIS's own flags. Pure."""
    ptypes = [(p[0], p[1], p[2]) for p in a["params"]]
    kinds = {t for _n, t, _d in ptypes}
    if in_allowlist:
        return "ALLOWLISTED", "already offered through run_allowlisted_processing_algorithm"
    if int(a["flags"]) & SECURITY_RISK_FLAG:
        return "EXCLUDE", "QGIS marks this algorithm SecurityRisk (it runs Python)"
    if a["provider"] in ("script", "model"):
        return "N/A", "user scripts and models"
    if a["provider"] == "grass":
        return "OPTIONAL-PROVIDER", "GRASS ships with some QGIS installs only (the CI image has it, a pip or distro install may not)"
    if a["provider"] in ("pdal", "3d") or kinds & SPECIAL_LAYER_TYPES:
        return "NEEDS-LAYER-TYPE", "works on point clouds / meshes / 3D tiles, which the plugin cannot load yet"
    bad = [n for n, t, d in ptypes if not d and t != "expression" and CODE_PARAM_NAMES.match(n)]
    if bad:
        return "EXCLUDE", f"free-form code / raw-argument parameter {bad} (same rule as #137)"
    if any(n.upper() == "URL" for n, _t, _d in ptypes) or "download" in a["id"]:
        return "EXCLUDE", "reaches the network with a model-written URL"
    if a["id"] == "native:rastercalc" or a["id"] == "native:virtualrastercalc":
        return "CANDIDATE-EXPRESSION", "QGIS raster-calculator grammar (QgsRasterCalculator parser, not Python eval); needs a parser check and a live test"
    if any(d and t in FILE_OUTPUT_TYPES for _n, t, d in ptypes):
        return "NEEDS-OUTPUT-HANDLING", "writes a file or folder: needs an export-style tool with a confirmed output path"
    if any((not d) and t in PATH_INPUT_TYPES for _n, t, d in ptypes):
        return "REVIEW-INPUT", "reads a file / folder / connection given as text"
    if any((not d) and t == "expression" for _n, t, d in ptypes):
        return "CANDIDATE-EXPRESSION", "takes a QGIS expression; same screening as field_calculator would be required"
    raw = [n for n, _t, d in ptypes if not d and RAW_ARGUMENT_PARAM_NAMES.match(n)]
    note = f"; the tool must refuse the raw-argument parameter(s) {raw}" if raw else ""
    return "CANDIDATE", "only layers, numbers, fields, enums, CRS, extents and sinks; needs a live test and parameter rules" + note


WAVE_BY_GROUP = {
    "Vector geometry": "2A geometry", "Vector overlay": "2A geometry", "Vector coverage": "2A geometry",
    "Vector table": "2B table and selection", "Vector selection": "2B table and selection", "Vector general": "2B table and selection",
    "Vector analysis": "2C analysis and creation", "Vector creation": "2C analysis and creation", "Network analysis": "2C analysis and creation",
    "Cartography": "2C analysis and creation", "Interpolation": "2C analysis and creation",
    "Raster analysis": "2D raster", "Raster creation": "2D raster", "Raster terrain analysis": "2D raster", "Raster tools": "2D raster",
    "Raster conversion": "2D raster", "Raster projections": "2D raster", "Raster miscellaneous": "2D raster", "Raster extraction": "2D raster",
    "Check geometry": "2E geometry quality", "Fix geometry": "2E geometry quality",
}


def wave_for(disposition, group):
    """Which build wave an algorithm belongs to in docs/QGIS_COVERAGE_GAP_ANALYSIS_2026-10-14.md. Pure."""
    if disposition == "ALLOWLISTED":
        return "done"
    if disposition in ("EXCLUDE", "N/A"):
        return "never"
    if disposition == "OPTIONAL-PROVIDER":
        return "7 optional provider"
    if disposition == "NEEDS-LAYER-TYPE":
        return "5 with new layer types"
    if disposition == "NEEDS-OUTPUT-HANDLING":
        return "4 export-style tool"
    if disposition == "REVIEW-INPUT":
        return "4 export-style tool"
    if disposition == "CANDIDATE-EXPRESSION":
        return "3 after expression screening"
    return WAVE_BY_GROUP.get(group, "2F other")


def processing_matrix(log_path):
    text = Path(log_path).read_text(encoding="utf-8", errors="replace")
    algs = []
    for line in text.splitlines():
        m = re.search(r"\bALG (\{.*\})\s*$", line)
        if m:
            algs.append(json.loads(m.group(1)))
    if not algs:
        raise SystemExit("no ALG lines found in the log")
    from cartogen_ai.core.agent.tools._processing_allowlist import ALLOWED_ALGORITHM_IDS
    ids_in_source = set(re.findall(r"""["']((?:native|gdal|qgis|3d|pdal|grass7|saga):[a-z0-9_]+)["']""",
                                   " ".join(p.read_text(encoding="utf-8") for p in (REPO / "src").rglob("*.py"))))
    rows = []
    for a in algs:
        disposition, reason = classify_algorithm(a, a["id"] in ALLOWED_ALGORITHM_IDS)
        rows.append({"id": a["id"], "name": a["name"], "group": a["group"], "provider": a["provider"],
                     "used_by_plugin_code": "yes" if a["id"] in ids_in_source else "no",
                     "in_allowlist": "yes" if a["id"] in ALLOWED_ALGORITHM_IDS else "no",
                     "disposition": disposition, "proposed_wave": wave_for(disposition, a["group"]), "reason": reason, "flags": a["flags"],
                     "param_types": "; ".join(sorted({p[1] for p in a["params"]}))})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry")
    ap.add_argument("--write-baseline", action="store_true", help="store today's per-action status as the floor tests/test_qgis_coverage_ratchet.py enforces")
    args = ap.parse_args()
    router = ToolRouter(TOOLS_SCHEMA)
    registered = {t["function"]["name"] for t in TOOLS_SCHEMA}
    OUT.mkdir(parents=True, exist_ok=True)
    rows = action_status(router, registered)
    write_csv(OUT / "actions_matrix.csv", rows)
    print(f"actions: {len(rows)}", dict(Counter(r["status"] for r in rows)))
    for area in sorted({r["area"] for r in rows}):
        c = Counter(r["status"] for r in rows if r["area"] == area)
        print(f"  {area:26s}", dict(c))
    if args.write_baseline:
        (OUT / "baseline.json").write_text(json.dumps({r["action"]: r["status"] for r in rows}, indent=1, ensure_ascii=False), encoding="utf-8")
        print("baseline written")
    if args.registry:
        prows = processing_matrix(args.registry)
        write_csv(OUT / "processing_matrix.csv", prows)
        print(f"processing: {len(prows)} algorithms", dict(Counter(r["disposition"] for r in prows)))


if __name__ == "__main__":
    main()
