#!/usr/bin/env python3
"""The extra input files the full smoke package needs, generated the same way every time (nothing random, no network, standard library only).

    python tools/make_full_smoke_fixtures.py OUT_DIR

The pinned smoke fixtures (docs/release_smoke_assets/inputs, docs/hand_test_v2_inputs) are never touched; these are the files no earlier package had:
  smoke_big_area.geojson     one polygon, about 220 km by 220 km, EPSG:4326: a 1 km task grid over it is above the 5,000 task limit
  before_fixture.asc/.prj, after_fixture.asc/.prj   two 20 x 20 ASCII grids (the second lower in the middle: a district that LOST value) with a WGS84 .prj
  smoke_many_points.csv      60,000 points (lon, lat) over Aden: a layer large enough to trigger the large-input warning of the MCP approval dialog
  smoke_multipoint.geojson   three MultiPoint features (2, 3 and 2 parts) with attributes, for obfuscate_sensitive_points
  smoke_mesh.2dm             a four-node mesh: a layer with no featureCount, for tidy_project_layers
  smoke_route.geojson        a 6 km route line in latitude/longitude running through Event A and Event B of smoke_events.csv (C and D lie about 1.5 km beyond its ends)
  smoke_prob.csv             a small forecast table whose probability column is 0-100 (percent)
  cartogen_profiles/smoke_cod.json   a map profile that flags COD boundaries with a test credit wording (validated by the plugin's own validator in the tests)
Each is a text file: it can be read by eye before anyone opens QGIS."""
import json
import sys
from pathlib import Path

WGS84_PRJ = ('GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],'
             'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]\n')


def big_area():
    ring = [[44.0, 12.0], [46.0, 12.0], [46.0, 14.0], [44.0, 14.0], [44.0, 12.0]]
    return json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": "smoke_big_area"}, "geometry": {"type": "Polygon", "coordinates": [ring]}}]}, indent=1) + "\n"


def asc(kind):
    """A 20 x 20 grid at 0.001 degrees from (44.9, 12.7). 'before' is a smooth slope; 'after' is the same with the middle 6 x 6 cells lowered by 40."""
    rows = []
    for r in range(20):
        values = []
        for c in range(20):
            value = 100 + 2 * c + r
            if kind == "after" and 7 <= r <= 12 and 7 <= c <= 12:
                value -= 40
            values.append(str(value))
        rows.append(" ".join(values))
    header = "ncols 20\nnrows 20\nxllcorner 44.9\nyllcorner 12.7\ncellsize 0.001\nNODATA_value -9999\n"
    return header + "\n".join(rows) + "\n"


def many_points(n=60000):
    lines = ["lon,lat,id"]
    side = 245                                               # 245 x 245 = 60,025 >= 60,000
    lines.extend(f"{44.90 + (i % side) * 0.0008:.5f},{12.70 + (i // side) * 0.0008:.5f},{i}" for i in range(n))
    return "\n".join(lines) + "\n"


def multipoint():
    def feature(name, parts):
        return {"type": "Feature", "properties": {"name": name, "category": "sensitive"}, "geometry": {"type": "MultiPoint", "coordinates": parts}}
    return json.dumps({"type": "FeatureCollection", "features": [
        feature("site_a", [[44.95, 12.75], [44.96, 12.76]]),
        feature("site_b", [[44.97, 12.77], [44.98, 12.78], [44.99, 12.79]]),
        feature("site_c", [[44.92, 12.72], [44.93, 12.73]])]}, indent=1) + "\n"


def mesh():
    return "MESH2D\nE3T 1 1 2 3 1\nE3T 2 2 4 3 1\nND 1 44.90 12.70 10\nND 2 44.91 12.70 12\nND 3 44.90 12.71 11\nND 4 44.91 12.71 13\n"


def route():
    return json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": "smoke_route"}, "geometry": {"type": "LineString", "coordinates": [[44.18, 15.35], [44.22, 15.39]]}}]}, indent=1) + "\n"


def forecast():
    return ("date,station,flow,prob\n2026-11-01,S1,120,80\n2026-11-02,S1,95,90\n2026-11-03,S1,130,55\n"
            "2026-11-01,S2,60,70\n2026-11-02,S2,110,65\n2026-11-03,S2,140,20\n")


def cod_profile():
    return json.dumps({"profile_version": 1, "name": "smoke_cod", "description": "Smoke test profile: COD boundaries with a test credit wording.",
                       "page_size": "A3", "orientation": "landscape", "export_preset": "web", "cod_boundaries": True,
                       "cod_credit": "Boundaries: Smoke Test Org COD (test wording)",
                       "required_elements": ["MAP_MAIN", "TITLE", "LEGEND", "SCALEBAR", "FOOTER"]}, indent=1) + "\n"


FILES = {
    "smoke_big_area.geojson": big_area,
    "before_fixture.asc": lambda: asc("before"), "before_fixture.prj": lambda: WGS84_PRJ,
    "after_fixture.asc": lambda: asc("after"), "after_fixture.prj": lambda: WGS84_PRJ,
    "smoke_many_points.csv": many_points,
    "smoke_multipoint.geojson": multipoint,
    "smoke_mesh.2dm": mesh,
    "smoke_route.geojson": route,
    "smoke_prob.csv": forecast,
    "cartogen_profiles/smoke_cod.json": cod_profile,
}


def write_all(out_dir):
    out = Path(out_dir)
    for name, make in FILES.items():
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(make(), encoding="utf-8", newline="\n")
    return sorted(FILES)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    print("\n".join(write_all(sys.argv[1])))
