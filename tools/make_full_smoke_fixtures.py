#!/usr/bin/env python3
"""The extra input files the full smoke package needs, generated the same way every time (nothing random, no network, standard library only).

    python tools/make_full_smoke_fixtures.py OUT_DIR

The pinned smoke fixtures (docs/release_smoke_assets/inputs, docs/hand_test_v2_inputs) are never touched; these are the files no earlier package had:
  smoke_big_area.geojson     one polygon, about 220 km by 220 km, EPSG:4326: a 1 km task grid over it is above the 5,000 task limit
  before_fixture.asc/.prj, after_fixture.asc/.prj   two 40 x 40 ASCII grids of 100 m cells in EPSG:32636 laid over smoke_admin (the second lower in the middle: a
                             district that LOST value), each with a UTM 36N .prj. The first version put them near Aden, 900 km from smoke_admin (hand run 2026-11-04)
  smoke_many_points.csv      60,000 points (lon, lat) over Aden: a layer large enough to trigger the large-input warning of the MCP approval dialog
  smoke_multipoint.geojson   three MultiPoint features (2, 3 and 2 parts) with attributes, for obfuscate_sensitive_points
  smoke_mesh.2dm             a four-node mesh: a layer with no featureCount, for tidy_project_layers
  smoke_route.geojson        a 6 km route line in latitude/longitude running through Event A and Event B of smoke_events.csv (C and D lie about 1.5 km beyond its ends)
  smoke_prob.csv             a small forecast table whose probability column is 0-100 (percent)
  cartogen_profiles/smoke_cod.json   a map profile that flags COD boundaries with a test credit wording (validated by the plugin's own validator in the tests)
  smoke_districts_cases.geojson  100 one-km squares ("districts", EPSG:32636) with cases, population, expected counts and four more numeric fields; a 3 x 3 block of high counts is planted at D33 to D55 (rows C21 to C26)
  smoke_checker4.geojson     a 4 x 4 checkerboard of +1 and -1: Moran's I with rook weights is exactly -1 (row C21)
  smoke_one_high5.geojson    a 5 x 5 grid of zeros with one 10 in the middle: Getis-Ord z is exactly 2.0 there with rook weights (row C22)
  smoke_rates3.geojson       three areas of 10, 20 and 30 cases in 1,000, 2,000 and 3,000 people: 1,000 per 100,000 each, relative risk 1 (row C24)
  smoke_worldcover.asc/.prj  a 40 x 40 classified raster of ESA WorldCover codes (10, 30, 40, 50, 80 and a 2 x 2 patch of 11, which is not a class) over the same ground as smoke_admin (row C20)
  smoke_change_classes.geojson  six polygons whose `change` field holds -1, 0, 1 as text and whose `change_word` field holds loss, stable, gain (row C20)
  smoke_clients.geojson      four FICTIONAL client addresses (row C27: tag it SENSITIVE; geocoding it must be refused)
  smoke_clinics.geojson      three landmark places (row C27: tag it PUBLIC; geocoding it must go ahead)
Each is a text file: it can be read by eye before anyone opens QGIS."""
import json
import sys
from pathlib import Path

UTM36N_PRJ = ('GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],'
             'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]\n')
UTM36N_PRJ = ('PROJCS["WGS_1984_UTM_Zone_36N",' + UTM36N_PRJ.strip() + ',PROJECTION["Transverse_Mercator"],PARAMETER["False_Easting",500000.0],'
              'PARAMETER["False_Northing",0.0],PARAMETER["Central_Meridian",33.0],PARAMETER["Scale_Factor",0.9996],PARAMETER["Latitude_Of_Origin",0.0],UNIT["Meter",1.0]]\n')


def big_area():
    ring = [[44.0, 12.0], [46.0, 12.0], [46.0, 14.0], [44.0, 14.0], [44.0, 12.0]]
    return json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": "smoke_big_area"}, "geometry": {"type": "Polygon", "coordinates": [ring]}}]}, indent=1) + "\n"


def asc(kind):
    """A 40 x 40 grid of 100 m cells from (775400, 3537600) in EPSG:32636: it covers smoke_admin (x 775580 to 778779, y 3537720 to 3540689). 'before' is a
    smooth slope; 'after' is the same with the middle 12 x 12 cells lowered by 40."""
    rows = []
    for r in range(40):
        values = []
        for c in range(40):
            value = 100 + 2 * c + r
            if kind == "after" and 14 <= r <= 25 and 14 <= c <= 25:
                value -= 40
            values.append(str(value))
        rows.append(" ".join(values))
    header = "ncols 40\nnrows 40\nxllcorner 775400\nyllcorner 3537600\ncellsize 100\nNODATA_value -9999\n"
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


# ---- PLAN-023 R2 / R3-6 / tracker 1.26 inputs (rows C20 to C27). Every number a row quotes is recomputed from these files by tests/test_r2_smoke_inputs.py.
CELL = 1000.0                       # metres; the squares of the district grids
ORIGIN = (775000.0, 3537000.0)     # lower left corner, EPSG:32636
CRS32636 = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::32636"}}


def _square(col, row, x0=ORIGIN[0], y0=ORIGIN[1], size=CELL):
    x, y = x0 + col * size, y0 + row * size
    return [[[x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]]]


def _collection(features, crs=CRS32636):
    doc = {"type": "FeatureCollection", "name": "smoke", "features": features}
    if crs:
        doc = {"type": "FeatureCollection", "name": "smoke", "crs": crs, "features": features}
    return json.dumps(doc, indent=1) + "\n"


def district_values():
    """The numbers of smoke_districts_cases.geojson, by (row, col). Pure. The block rows 3 to 5, columns 3 to 5 is the planted cluster; D00, D09, D90 and D99 hold fewer than 5 cases."""
    values = {}
    for r in range(10):
        for c in range(10):
            block = 3 <= r <= 5 and 3 <= c <= 5
            cases = 15 if block else 5 + (r * 3 + c * 2) % 4            # 5 to 8 on the background, so a rate map has several classes
            cases = {(0, 0): 4, (0, 9): 3, (9, 0): 0, (9, 9): 2}.get((r, c), cases)
            values[(r, c)] = {
                "name": f"D{r}{c}", "cases": cases, "population": 1000, "expected": 7.07,
                "burglaries": 2 + (6 if block else 0) + (r + c) % 3,            # a block of high counts on a gentle background
                "vacant_buildings": 10 + (14 if block else 0) + (r * c) % 4,
                "price_index": 100 + (40 if block else 0) + (r + 2 * c) % 5,
                "pm25": 12 + (20 if block else 0) + (3 * r + c) % 4,
            }
    return values


def districts_cases():
    feats = [{"type": "Feature", "properties": {"id": r * 10 + c, **v}, "geometry": {"type": "Polygon", "coordinates": _square(c, r)}}
             for (r, c), v in sorted(district_values().items())]
    return _collection(feats)


def checker4():
    feats = [{"type": "Feature", "properties": {"name": f"K{r}{c}", "v": float((-1) ** (r + c))}, "geometry": {"type": "Polygon", "coordinates": _square(c, r)}}
             for r in range(4) for c in range(4)]
    return _collection(feats)


def one_high5():
    feats = [{"type": "Feature", "properties": {"name": f"H{r}{c}", "v": 10.0 if (r, c) == (2, 2) else 0.0}, "geometry": {"type": "Polygon", "coordinates": _square(c, r)}}
             for r in range(5) for c in range(5)]
    return _collection(feats)


def rates3():
    rows = [("R1", 10, 1000, 8.0), ("R2", 20, 2000, 25.0), ("R3", 30, 3000, 30.0)]
    feats = [{"type": "Feature", "properties": {"name": n, "cases": c, "population": p, "expected": e}, "geometry": {"type": "Polygon", "coordinates": _square(i, 0)}}
             for i, (n, c, p, e) in enumerate(rows)]
    return _collection(feats)


def worldcover():
    """40 x 40 cells of 100 m on the grid of before_fixture.asc. 10 tree cover (north-west), 40 cropland (north-east), 30 grassland (south), 50 built-up (a block in the
    south-west), 80 water (the bottom three rows) and a 2 x 2 patch of 11, which is NOT a WorldCover class (it must be drawn grey and named, never recoloured)."""
    rows = []
    for r in range(40):
        values = []
        for c in range(40):
            value = 30
            if r < 20 and c < 20:
                value = 10
            elif r < 20:
                value = 40
            if 26 <= r <= 33 and 6 <= c <= 13:
                value = 50
            if r >= 37:
                value = 80
            if 10 <= r <= 11 and 30 <= c <= 31:
                value = 11
            values.append(str(value))
        rows.append(" ".join(values))
    header = "ncols 40\nnrows 40\nxllcorner 775400\nyllcorner 3537600\ncellsize 100\nNODATA_value -9999\n"
    return header + "\n".join(rows) + "\n"


def change_classes():
    pairs = [("-1", "loss"), ("0", "stable"), ("1", "gain"), ("-1", "loss"), ("0", "stable"), ("1", "gain")]
    feats = [{"type": "Feature", "properties": {"name": f"X{i}", "change": a, "change_word": b}, "geometry": {"type": "Polygon", "coordinates": _square(i % 3, i // 3, ORIGIN[0] + 12000.0, ORIGIN[1])}}
             for i, (a, b) in enumerate(pairs)]
    return _collection(feats)


def _points(rows, crs=None):
    feats = [{"type": "Feature", "properties": props, "geometry": {"type": "Point", "coordinates": [lon, lat]}} for props, lon, lat in rows]
    return json.dumps({"type": "FeatureCollection", "name": "smoke", "features": feats}, indent=1) + "\n"


def clients():
    return _points([({"case_id": "K-001", "address": "Flat 3, 12 Example Street, Crater, Aden"}, 45.036, 12.786),
                    ({"case_id": "K-002", "address": "7 Sample Lane, Khormaksar, Aden"}, 45.019, 12.829),
                    ({"case_id": "K-003", "address": "Block C, 41 Fictional Road, Sheikh Othman, Aden"}, 44.988, 12.865),
                    ({"case_id": "K-004", "address": "House 9, Test Quarter, Tawahi, Aden"}, 44.995, 12.775)])


def clinics():
    return _points([({"name": "Airport", "address": "Aden International Airport, Aden, Yemen"}, 45.028, 12.829),
                    ({"name": "Fortress", "address": "Sira Fortress, Crater, Aden, Yemen"}, 45.040, 12.783),
                    ({"name": "Harbour", "address": "Port of Aden, Aden, Yemen"}, 44.995, 12.790)])


FILES = {
    "smoke_big_area.geojson": big_area,
    "before_fixture.asc": lambda: asc("before"), "before_fixture.prj": lambda: UTM36N_PRJ,
    "after_fixture.asc": lambda: asc("after"), "after_fixture.prj": lambda: UTM36N_PRJ,
    "smoke_many_points.csv": many_points,
    "smoke_multipoint.geojson": multipoint,
    "smoke_mesh.2dm": mesh,
    "smoke_route.geojson": route,
    "smoke_prob.csv": forecast,
    "cartogen_profiles/smoke_cod.json": cod_profile,
    "smoke_districts_cases.geojson": districts_cases,
    "smoke_checker4.geojson": checker4,
    "smoke_one_high5.geojson": one_high5,
    "smoke_rates3.geojson": rates3,
    "smoke_worldcover.asc": worldcover, "smoke_worldcover.prj": lambda: UTM36N_PRJ,
    "smoke_change_classes.geojson": change_classes,
    "smoke_clients.geojson": clients,
    "smoke_clinics.geojson": clinics,
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
