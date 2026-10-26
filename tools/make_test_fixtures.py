"""Write the small, invented fixture files used by the 1.18.2+ hand-test package (no network, no third-party packages).

Everything is made up, around Aden (EPSG:4326): six 0.1 x 0.1 degree "districts" in a 3 x 2 grid, a road grid on their edges, two
hospitals, a destroyed bridge, before/after damage rasters and a population raster on one 0.01 degree grid, buildings, a survey, a
JIAF HXL table, a 3W table and forecasts. Values are chosen so a tester can predict the answer (see README_FIXTURES.md written
alongside). Usage: python tools/make_test_fixtures.py OUTPUT_DIR
"""
import csv
import json
import os
import sys

LON0, LAT0, STEP = 44.9, 12.75, 0.1
DISTRICTS = [  # pcode, name, governorate, people_in_need, displaced, water_gap(%), ipc, households
    ("YE2001", "Crater", "Aden", 52000, 4000, 62, 4, 9000),
    ("YE2002", "Sira", "Aden", 31000, 1500, 35, 3, 6000),
    ("YE2003", "Khormaksar", "Aden", 76000, 9000, 80, 4, 12000),
    ("YE2004", "Dar Saad", "Lahj", 18000, 700, 20, 2, 4000),
    ("YE2005", "Tur al Bahah", "Lahj", 94000, 15000, 91, 5, 15000),
    ("YE2006", "Habil Jabr", "Lahj", 12000, 300, 15, 2, 3000),
]


def _write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def _geojson(path, features):
    _write(path, json.dumps({"type": "FeatureCollection", "features": features}, indent=1))


def _csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerows(rows)


def _poly(x, y, w, h):
    return {"type": "Polygon", "coordinates": [[[x, y], [x + w, y], [x + w, y + h], [x, y + h], [x, y]]]}


def _cell(i):
    return LON0 + (i % 3) * STEP, LAT0 + (i // 3) * STEP


def _asc(path, fn, cols=30, rows=20, cell=0.01):
    # ESRI ASCII grid: QGIS reads it directly; the .prj sets EPSG:4326 so no CRS prompt appears.
    lines = [f"ncols {cols}", f"nrows {rows}", f"xllcorner {LON0}", f"yllcorner {LAT0}", f"cellsize {cell}", "NODATA_value -9999"]
    # first line is the northern row
    lines.extend(" ".join(f"{fn(c, rows - 1 - r):.3f}" for c in range(cols)) for r in range(rows))
    _write(path, "\n".join(lines) + "\n")
    _write(path[:-4] + ".prj", 'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],'
                               'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]\n')


def main(out):
    os.makedirs(out, exist_ok=True)
    feats = []
    for i, (pc, name, gov, pin, disp, water, ipc, hh) in enumerate(DISTRICTS):
        x, y = _cell(i)
        feats.append({"type": "Feature", "geometry": _poly(x, y, STEP, STEP),
                      "properties": {"ADM2_PCODE": pc, "ADM2_EN": name, "ADM1_EN": gov, "people_in_need": pin, "displaced": disp,
                                     "water_gap": water, "ipc_phase": ipc, "households": hh}})
    _geojson(f"{out}/admin_units_fixture.geojson", feats)
    dup = json.loads(json.dumps(feats))
    dup[5]["properties"]["ADM2_PCODE"] = "YE2001"  # a deliberate duplicate for check_pcode_uniqueness
    _geojson(f"{out}/admin_units_duplicate_pcode_fixture.geojson", dup)

    # Damage: the after raster loses value in the Khormaksar (cell 2) and Tur al Bahah (cell 4) blocks.
    def before(c, r):
        return 100.0

    def after(c, r):
        d = 100.0
        if 20 <= c < 30 and 0 <= r < 10:
            d = 30.0  # Khormaksar block
        if 10 <= c < 20 and 10 <= r < 20:
            d = 55.0  # Tur al Bahah block
        return d
    _asc(f"{out}/before_fixture.asc", before)
    _asc(f"{out}/after_fixture.asc", after)
    _asc(f"{out}/population_fixture.asc", lambda c, r: 5.0 + (c % 7) + (r % 5))

    b = []
    for i in range(6):
        x, y = _cell(i)
        for k in range(i + 2):  # 2..7 buildings per district
            bx, by = x + 0.02 + 0.01 * k, y + 0.03
            b.append({"type": "Feature", "geometry": _poly(bx, by, 0.004, 0.004), "properties": {"id": f"b{i}{k}"}})
    _geojson(f"{out}/buildings_fixture.geojson", b)

    # Road grid on the district edges; a field speed_kmh; two hospitals at junctions; a bridge on one segment.
    roads, rid = [], 0
    for j, lat in enumerate((LAT0, LAT0 + STEP, LAT0 + 2 * STEP)):
        for i in range(3):
            rid += 1
            roads.append((f"R{rid}", 50 if j != 1 else 30, [[LON0 + i * STEP, lat], [LON0 + (i + 1) * STEP, lat]]))
    for i in range(4):
        for j in range(2):
            rid += 1
            roads.append((f"R{rid}", 40, [[LON0 + i * STEP, LAT0 + j * STEP], [LON0 + i * STEP, LAT0 + (j + 1) * STEP]]))
    _geojson(f"{out}/roads_grid_fixture.geojson", [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": c},
                                                    "properties": {"road_id": r, "speed_kmh": s, "highway": "primary"}} for r, s, c in roads])
    pt = lambda x, y, **p: {"type": "Feature", "geometry": {"type": "Point", "coordinates": [x, y]}, "properties": p}  # noqa: E731
    _geojson(f"{out}/hospitals_grid_fixture.geojson", [pt(LON0, LAT0, name="H1 Aden General"), pt(LON0 + 3 * STEP, LAT0 + 2 * STEP, name="H2 Lahj")])
    _geojson(f"{out}/origin_fixture.geojson", [pt(LON0, LAT0, name="Depot")])
    _geojson(f"{out}/bridges_grid_fixture.geojson", [pt(LON0 + 1.5 * STEP, LAT0, name="B1 destroyed bridge")])
    _geojson(f"{out}/convoy_route_fixture.geojson", [{"type": "Feature", "geometry": {"type": "LineString",
             "coordinates": [[LON0, LAT0], [LON0 + 3 * STEP, LAT0]]}, "properties": {"name": "Convoy route"}}])
    _geojson(f"{out}/incidents_fixture.geojson", [pt(LON0 + 0.1, LAT0 + 0.002, incident_date="2026-10-20", severity=3),
                                                   pt(LON0 + 0.2, LAT0 + 0.0005, incident_date="2026-10-05", severity=5),
                                                   pt(LON0 + 0.15, LAT0 + 0.08, incident_date="2026-10-22", severity=2)])

    rows = [["governorate", "water_access", "weight"]]
    for gov, n_no, n_yes in (("Aden", 12, 8), ("Lahj", 6, 14), ("Taiz", 3, 4)):  # Taiz has 7 respondents: under min 10
        rows += [[gov, "No access", 1.0] for _ in range(n_no)] + [[gov, "Access", 1.0] for _ in range(n_yes)]
    _csv(f"{out}/msna_fixture.csv", rows)

    _csv(f"{out}/jiaf_hxl_fixture.csv", [
        ["Gov_PCODE", "Governorate", "Dis_PCODE", "District", "Severity", "Total PiN", "Total PiN", "Severity", "Total PiN", "Severity"],
        ["#adm1 +code", "#adm1 +name", "#adm2 +code", "#adm2 +name", "#severity", "#inneed", "#inneed +wsh", "#severity +wsh", "#inneed +shl", "#severity +shl"],
        ["YE20", "Aden", "YE2001", "Crater", 3, 52000, 40000, 3, 30000, 4],
        ["YE20", "Aden", "YE2002", "Sira", 3, 31000, 25000, 3, 12000, 3],
        ["YE20", "Aden", "YE2003", "Khormaksar", 4, 76000, 60000, 4, 70000, 4],
        ["YE25", "Lahj", "YE2004", "Dar Saad", 2, 18000, 9000, 2, 18000, 3],
        ["YE25", "Lahj", "YE2005", "Tur al Bahah", 5, 94000, 90000, 5, 80000, 4],
        ["YE25", "Lahj", "YE2006", "Habil Jabr", 2, 12000, 7000, 2, 5000, 2],
    ])

    # 3W: no activity in Habil Jabr and Tur al Bahahso Tur al Bahah (severe) is the presence gap to find.
    _csv(f"{out}/3w_fixture.csv", [["admin_pcode", "organization", "sector"], ["YE2001", "Org A", "WASH"], ["YE2001", "Org B", "Health"],
                                   ["YE2002", "Org A", "WASH"], ["YE2003", "Org C", "Shelter"], ["YE2004", "Org B", "Health"]])

    fc = [["district", "valid_date", "rain_mm", "prob", "prob_pct"], ["Aden", "2026-10-27", 85, 0.8, 80], ["Aden", "2026-10-28", 20, 0.4, 40],
          ["Lahj", "2026-10-27", 90, 0.5, 50], ["Taiz", "2026-10-28", 40, 0.9, 90], ["Taiz", "2026-11-20", 120, 0.9, 90]]
    _csv(f"{out}/forecast_fixture.csv", fc)
    _write(f"{out}/README_FIXTURES.md", __doc__.split("Usage")[0] + """
Predictable answers (for the corrected scenario prompts):
- admin_units_duplicate_pcode_fixture: YE2001 appears twice -> check_pcode_uniqueness reports it. admin_units_fixture is clean.
- before/after rasters: after is lower by 70 in Khormaksar (YE2003) and by 45 in Tur al Bahah (YE2005); the others do not change.
  Both rasters share one grid. Building counts per district: 2, 3, 4, 5, 6, 7.
- roads_grid_fixture: speed_kmh 50 on the south and north edges, 30 on the middle edge, 40 on the vertical edges. H1 is at the
  south-west corner, H2 at the north-east corner, Depot = H1. The destroyed bridge sits on the middle of the SECOND south segment
  (between the first and second vertical roads); a 500 m barrier buffer blocks that segment only, so routes from H1 to the east
  go up and around through the 30 km/h middle edge. One degree is about 111 km, so each edge is about 11 km long.
- msna_fixture: Aden 20 respondents (12 no access = 60%), Lahj 20 (6 = 30%), Taiz 7 -> suppressed with min 10.
- forecast_fixture, rain_mm >= 50, lead 3 days from 2026-10-26: Aden (85) and Lahj (90) activate; Taiz does not (max 40 inside
  the window; its 120 mm row is dated 2026-11-20, outside it). Adding "probability at least 70%" on prob_pct (0-100) keeps Aden
  (80) and drops Lahj (50); the same rule on the 0-1 column prob is 0.7.
- 3w_fixture: no activity row for YE2005 (the highest need) or YE2006 -> presence gap on YE2005 expected.
- jiaf_hxl_fixture: two sectors (wash, shelter) only, so intersectoral severity is incomplete and the result says so.
- convoy route runs along the south edge; incidents: one within ~200 m (2026-10-20), one within ~50 m dated 2026-10-05, older than 30 days if
  you ask as of 2026-11-10, one 8 km north (outside any 500 m buffer).
All of it is invented for testing and describes no real place or event.
""")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "fixtures")
