"""Agent-run smoke runner: runs the rows of docs/AGENT_RUN_ROWS.json against the real plugin tools in a real (headless) QGIS and writes every
evidence file itself. No model, no network, no clicking, no clipboard. Run it with QGIS's own Python (Windows: the python-qgis.bat of the QGIS install):

    python-qgis.bat run_smoke_headless.py --out C:\\Cartogen-AI-Smoke\\run1 [--rows H1-rates-crude,H2-moran-checkerboard] [--plugin-src <folder that holds cartogen_ai>]

Writes OUT\\inputs\\ (the shipped fixtures), OUT\\evidence\\<row>\\ (row.json: every step's arguments, result and timing, the layer table and sha256 of any file a tool wrote;
checks.txt; verdict.json), OUT\\RESULTS.csv and OUT\\SUMMARY.md. Exit code 0 only if every selected row is PASS and the evidence is complete (tools/smoke_core.verify_evidence).

Status: tools/smoke_core.py is covered offline by tests/test_smoke_core.py; this QGIS half is exercised by tests/test_run_smoke_headless_live.py in the QGIS CI job. NOT yet run on a
real Windows QGIS by hand: the first such run is the dry run in the package README."""
import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import smoke_core as core  # noqa: E402

ROWS_FILE = HERE.parent / "docs" / "AGENT_RUN_ROWS.json"


def find_plugin_src(hint):
    """The folder that contains the cartogen_ai package, from --plugin-src, the repo's src/, or next to this script. Pure apart from reads."""
    for base in [Path(hint)] if hint else [HERE.parent / "src", HERE.parent, HERE]:
        for cand in (base, *sorted(p for p in base.glob("*") if p.is_dir())) if base.is_dir() else ():
            if (cand / "cartogen_ai" / "core").is_dir():
                return cand
    return None


def boot_qgis():
    from qgis.core import QgsApplication
    app = QgsApplication([b"smoke-runner"], False)
    QgsApplication.setPrefixPath(os.environ.get("QGIS_PREFIX_PATH", "/usr"), True)
    app.initQgis()
    plugins = os.path.join(QgsApplication.pkgDataPath(), "python", "plugins")
    if os.path.isdir(plugins) and plugins not in sys.path:
        sys.path.insert(0, plugins)
    return app


def layer_table():
    from qgis.core import QgsProject
    return [{"name": layer.name(), "type": str(layer.type()), "provider": layer.providerType() if hasattr(layer, "providerType") else "",
             "crs": layer.crs().authid(), "features": layer.featureCount() if hasattr(layer, "featureCount") else None,
             "fields": [f.name() for f in layer.fields()] if hasattr(layer, "fields") else []}
            for layer in QgsProject.instance().mapLayers().values()]


def layer_values(name, field):
    from qgis.core import QgsProject
    layers = QgsProject.instance().mapLayersByName(name)
    if not layers or layers[0].fields().indexFromName(field) < 0:
        return None
    return [f[field] for f in layers[0].getFeatures()]


def run_row(row, inputs_dir, registry, out_dir):
    from qgis.core import QgsProject, QgsVectorLayer
    QgsProject.instance().clear()
    record = {"steps": [], "results": [], "timings_ms": [], "error": None}
    results = []
    try:
        for step in row["steps"]:
            started = time.monotonic()
            kind = step["do"]
            if kind == "load":
                layer = QgsVectorLayer(str(Path(inputs_dir) / step["file"]), step["name"], "ogr")
                if not layer.isValid():
                    raise RuntimeError(f"could not load {step['file']}")
                QgsProject.instance().addMapLayer(layer)
                result = {"loaded": step["name"], "features": layer.featureCount()}
            elif kind == "load_raster":
                from qgis.core import QgsRasterLayer
                raster = QgsRasterLayer(str(Path(inputs_dir) / step["file"]), step["name"])
                if not raster.isValid():
                    raise RuntimeError(f"could not load {step['file']}")
                QgsProject.instance().addMapLayer(raster)
                result = {"loaded": step["name"], "width": raster.width(), "height": raster.height()}
            elif kind == "tag":
                from cartogen_ai.core.models import sensitivity
                layer = QgsProject.instance().mapLayersByName(step["layer"])[0]
                sensitivity.set_layer_sensitivity(layer, step["level"], "agent-run smoke")
                result = {"tagged": step["layer"], "level": step["level"]}
            elif kind == "tool":
                func = registry.get(step["name"])
                result = func(**step["args"]) if func else {"error": f"Unknown tool: {step['name']}"}
            else:
                raise RuntimeError(f"unknown step kind {kind!r}")
            results.append(result)
            record["steps"].append(step)
            record["results"].append(result)
            record["timings_ms"].append(round((time.monotonic() - started) * 1000, 1))
    except Exception:
        record["error"] = traceback.format_exc()
    record["layers"] = layer_table()
    from cartogen_ai.core.agent.evidence import output_files
    record["output_files"] = [{"path": p, "sha256": core.sha256_of(p)} for r in results for p in output_files(r)]
    outcomes = [core.evaluate(c, results, layer_values) for c in row.get("checks", [])]
    status = core.verdict(outcomes, error=record["error"], needs_eyes=bool(row.get("needs_eyes")))
    core.write_row(out_dir, row, record, outcomes, status, note=(record["error"] or "").splitlines()[-1] if record["error"] else "")
    return status


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--rows", default="")
    ap.add_argument("--plugin-src", default="")
    ap.add_argument("--rows-file", default=str(ROWS_FILE))
    args = ap.parse_args(argv)
    src = find_plugin_src(args.plugin_src)
    if src is None:
        print("cannot find the cartogen_ai package; pass --plugin-src <folder that contains cartogen_ai>")
        return 2
    sys.path.insert(0, str(src))
    all_rows = json.loads(Path(args.rows_file).read_text(encoding="utf-8"))["rows"]
    wanted = [r for r in args.rows.split(",") if r]
    rows = [r for r in all_rows if not wanted or r["id"] in wanted]
    unknown = sorted(set(wanted) - {r["id"] for r in all_rows})
    if unknown or not rows:
        print(f"no such row(s): {unknown or wanted}")
        return 2
    out = Path(args.out)
    app = boot_qgis()
    try:
        statuses, problems = run_rows(rows, out)
    finally:
        app.exitQgis()
    for p in problems:
        print("EVIDENCE PROBLEM:", p)
    return 0 if not problems and all(s == "PASS" for s in statuses.values()) else 1


def run_rows(rows, out):
    """Writes the fixtures, runs every row in an already-booted QGIS, writes RESULTS.csv/SUMMARY.md and returns ({row id: status}, evidence problems)."""
    inputs = Path(out) / "inputs"
    import make_full_smoke_fixtures as fx
    fx.write_all(inputs)
    import cartogen_ai.core.agent.tools  # noqa: F401  (registers every tool)
    from cartogen_ai.core.agent.tools.registry import TOOL_REGISTRY
    statuses = {}
    try:
        for row in rows:
            statuses[row["id"]] = run_row(row, inputs, TOOL_REGISTRY, out)
            print(f"{row['id']}: {statuses[row['id']]}")
    finally:
        core.write_results(out, rows, statuses)
    return statuses, core.verify_evidence(out, [r["id"] for r in rows])


if __name__ == "__main__":
    sys.exit(main())
