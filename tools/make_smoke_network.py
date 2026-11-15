#!/usr/bin/env python3
"""Writes docs/release_smoke_assets/inputs/smoke_network.gpkg: the synthetic road network, facilities and edge-case layers that the open-issue
rows of the live test need, in the same UTM 36N area as smoke_data.gpkg. Standard library only (a GeoPackage is a SQLite file); deterministic, so
running it twice gives the same layers.

    python tools/make_smoke_network.py            # writes the file
    python tools/make_smoke_network.py --check    # exits 1 if the file on disk differs from what this script would write

Why a script and not a hand-made file: the layers are small and exist to trigger specific defects (a Geofabrik-style `oneway` column holding
F / T / B, duplicate and empty names, a layer in another CRS, a U-shaped road), so the recipe has to be readable and re-runnable. All data is
invented; nothing is taken from a real place. Verified here only by reading it back with sqlite3; opening it in QGIS is checked by
tests/test_smoke_network_live.py in the QGIS CI job.

Layers (all EPSG:32636 unless stated):
  smoke_roads            LINESTRING  grid of 24 road segments; oneway F / T / B (Geofabrik encoding) and a few empty, speed_kmh with NULLs, highway classes
  smoke_facilities       POINT       8 health facilities: a duplicate name, an empty name, one far off the network
  smoke_admin_dup        POLYGON     4 districts: two named Al-Dhale, one with no name
  smoke_points_4326      POINT       the five smoke_points in EPSG:4326 (lon/lat), for the mixed-CRS rows
  smoke_hubs_4326        POINT       the three smoke_hubs in EPSG:4326
  smoke_ubend_road       LINESTRING  one U-shaped road
  smoke_ubend_facilities POINT       a facility inside the U (close in a straight line, far along the road) and one beside an arm
"""
import math
import sqlite3
import struct
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "docs" / "release_smoke_assets" / "inputs" / "smoke_data.gpkg"
OUT = REPO / "docs" / "release_smoke_assets" / "inputs" / "smoke_network.gpkg"
STAMP = "2026-10-13T00:00:00.000Z"        # fixed, so the file is reproducible

# ---------------------------------------------------------------------------------------------- UTM 36N <-> WGS84 (Kruger series)
_A, _F = 6378137.0, 1 / 298.257223563
_K0, _E0, _LON0 = 0.9996, 500000.0, math.radians(33.0)
_N = _F / (2 - _F)
_AA = _A / (1 + _N) * (1 + _N ** 2 / 4 + _N ** 4 / 64)
_ALPHA = (_N / 2 - 2 * _N ** 2 / 3 + 5 * _N ** 3 / 16, 13 * _N ** 2 / 48 - 3 * _N ** 3 / 5, 61 * _N ** 3 / 240)
_BETA = (_N / 2 - 2 * _N ** 2 / 3 + 37 * _N ** 3 / 96, _N ** 2 / 48 + _N ** 3 / 15, 17 * _N ** 3 / 480)
_DELTA = (2 * _N - 2 * _N ** 2 / 3 - 2 * _N ** 3, 7 * _N ** 2 / 3 - 8 * _N ** 3 / 5, 56 * _N ** 3 / 15)


def utm36_to_lonlat(easting, northing):
    xi = northing / (_K0 * _AA)
    eta = (easting - _E0) / (_K0 * _AA)
    xi_p = xi - sum(_BETA[j] * math.sin(2 * (j + 1) * xi) * math.cosh(2 * (j + 1) * eta) for j in range(3))
    eta_p = eta - sum(_BETA[j] * math.cos(2 * (j + 1) * xi) * math.sinh(2 * (j + 1) * eta) for j in range(3))
    chi = math.asin(math.sin(xi_p) / math.cosh(eta_p))
    lat = chi + sum(_DELTA[j] * math.sin(2 * (j + 1) * chi) for j in range(3))
    lon = _LON0 + math.atan2(math.sinh(eta_p), math.cos(xi_p))
    return math.degrees(lon), math.degrees(lat)


def lonlat_to_utm36(lon, lat):
    phi, lam = math.radians(lat), math.radians(lon) - _LON0
    e = math.sqrt(_F * (2 - _F))
    t = math.sinh(math.atanh(math.sin(phi)) - e * math.atanh(e * math.sin(phi)))
    xi_p = math.atan2(t, math.cos(lam))
    eta_p = math.atanh(math.sin(lam) / math.sqrt(1 + t * t))
    xi = xi_p + sum(_ALPHA[j] * math.sin(2 * (j + 1) * xi_p) * math.cosh(2 * (j + 1) * eta_p) for j in range(3))
    eta = eta_p + sum(_ALPHA[j] * math.cos(2 * (j + 1) * xi_p) * math.sinh(2 * (j + 1) * eta_p) for j in range(3))
    return _E0 + _K0 * _AA * eta, _K0 * _AA * xi


# ---------------------------------------------------------------------------------------------------------- GeoPackage geometry
def _blob(srs, wkb):
    return b"GP" + bytes([0, 0x01]) + struct.pack("<i", srs) + wkb       # version 0, little-endian flags, no envelope


def point(srs, x, y):
    return _blob(srs, struct.pack("<BIdd", 1, 1, x, y))


def line(srs, pts):
    return _blob(srs, struct.pack("<BII", 1, 2, len(pts)) + b"".join(struct.pack("<dd", x, y) for x, y in pts))


def polygon(srs, ring):
    ring = list(ring) + ([ring[0]] if ring[0] != ring[-1] else [])
    return _blob(srs, struct.pack("<BIII", 1, 3, 1, len(ring)) + b"".join(struct.pack("<dd", x, y) for x, y in ring))


# -------------------------------------------------------------------------------------------------------------------- the layers
XS = [775900.0, 776700.0, 777500.0, 778300.0]
YS = [3538000.0, 3538800.0, 3539600.0, 3540400.0]


def roads():
    """24 segments of a 4 x 4 grid, encoded the way Geofabrik shapefile extracts are: oneway is F (forward only), T (against the digitised
    direction) or B (both), and empty on a few roads. (OSM's own yes / -1 / no is deliberately NOT used: the tool recognises the F/T/B
    encoding only when the layer holds nothing but F, T, B and empties, issue 132.) Column 3 is one-way northwards (F), row 3 one-way
    towards the west (T). speed_kmh is empty on every fifth segment (a road with no speed)."""
    out, n = [], 0
    for j, y in enumerate(YS):
        for i in range(3):
            n += 1
            oneway = None if n % 7 == 0 else ("T" if j == 2 else "B")
            out.append((n, f"Row {j + 1} east {i + 1}", "secondary" if j in (0, 3) else "residential", oneway,
                        None if n % 5 == 0 else (60.0 if j in (0, 3) else 30.0), [(XS[i], y), (XS[i + 1], y)]))
    for i, x in enumerate(XS):
        for j in range(3):
            n += 1
            oneway = None if n % 7 == 0 else ("F" if i == 2 else "B")
            out.append((n, f"Column {i + 1} north {j + 1}", "primary" if i in (0, 3) else "residential", oneway,
                        None if n % 5 == 0 else (80.0 if i in (0, 3) else 30.0), [(x, YS[j]), (x, YS[j + 1])]))
    return out


FACILITIES = [          # (name, type, x, y): offsets of 40-120 m from a road, except Remote_PHC, which is ~900 m from any road
    ("Al Noor Clinic", "clinic", 776000.0, 3538150.0),
    ("Al Noor Clinic", "clinic", 777400.0, 3539500.0),             # same name, different place
    (None, "clinic", 776800.0, 3539000.0),                         # no name
    ("Central Hospital", "hospital", 777580.0, 3538900.0),
    ("East PHC", "phc", 778250.0, 3539700.0),
    ("North Clinic", "clinic", 776650.0, 3540330.0),
    ("South Hospital", "hospital", 776750.0, 3538060.0),
    ("Remote_PHC", "phc", 779000.0, 3541400.0),                    # far off the network
]

ADMIN_DUP = [           # (name, population, need, [corners])
    ("Al-Dhale", 4200, 6, [(775600, 3537800), (777000, 3537800), (777000, 3539200), (775600, 3539200)]),
    ("Al-Dhale", 3100, 8, [(777000, 3537800), (778600, 3537800), (778600, 3539200), (777000, 3539200)]),   # same name, other polygon
    (None, 2500, 4, [(775600, 3539200), (777000, 3539200), (777000, 3540600), (775600, 3540600)]),         # no name
    ("Taiz", 5000, 9, [(777000, 3539200), (778600, 3539200), (778600, 3540600), (777000, 3540600)]),
]

def ubend_geometry():
    """A U opening northwards: down the west arm, along the bottom, up the east arm. 600 m wide, 400 m deep: a point in the middle of the
    U is 300 m from either arm in a straight line but ~1.2 km away along the road."""
    base_x, base_y = 777700.0, 3540900.0
    road = [(base_x, base_y + 400.0), (base_x, base_y), (base_x + 600.0, base_y), (base_x + 600.0, base_y + 400.0)]
    inside = (base_x + 300.0, base_y + 330.0)                       # in the open mouth of the U
    beside = (base_x - 80.0, base_y + 200.0)                        # next to the west arm, outside the U
    return road, inside, beside


def smoke_source_points():
    with sqlite3.connect(SRC) as src:
        def pts(table):
            out = []
            for name, blob in src.execute(f"SELECT name, geom FROM {table} ORDER BY fid"):  # noqa: S608  (constant table names)
                x, y = struct.unpack("<dd", blob[8 + 5:8 + 5 + 16])       # 8-byte GPKG header, 1+4 byte WKB header
                out.append((name, x, y))
            return out
        return pts("smoke_points"), pts("smoke_hubs")


# ------------------------------------------------------------------------------------------------------------------------ writer
def write(path):
    path = Path(path)
    if path.exists():
        path.unlink()
    pts, hubs = smoke_source_points()
    with sqlite3.connect(path) as db, sqlite3.connect(SRC) as src:
        db.execute("PRAGMA application_id = 1196444487")
        db.execute("PRAGMA user_version = 10400")
        db.executescript("""
CREATE TABLE gpkg_spatial_ref_sys (srs_name TEXT NOT NULL, srs_id INTEGER PRIMARY KEY, organization TEXT NOT NULL,
  organization_coordsys_id INTEGER NOT NULL, definition TEXT NOT NULL, description TEXT);
CREATE TABLE gpkg_contents (table_name TEXT NOT NULL PRIMARY KEY, data_type TEXT NOT NULL, identifier TEXT UNIQUE, description TEXT DEFAULT '',
  last_change DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')), min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE, srs_id INTEGER,
  CONSTRAINT fk_gc_r_srs_id FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id));
CREATE TABLE gpkg_geometry_columns (table_name TEXT NOT NULL, column_name TEXT NOT NULL, geometry_type_name TEXT NOT NULL, srs_id INTEGER NOT NULL,
  z TINYINT NOT NULL, m TINYINT NOT NULL, CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name), CONSTRAINT uk_gc_table_name UNIQUE (table_name),
  CONSTRAINT fk_gc_tn FOREIGN KEY (table_name) REFERENCES gpkg_contents(table_name), CONSTRAINT fk_gc_srs FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys (srs_id));
""")
        db.executemany("INSERT INTO gpkg_spatial_ref_sys VALUES (?,?,?,?,?,?)", src.execute("SELECT * FROM gpkg_spatial_ref_sys ORDER BY srs_id"))

        def layer(name, gtype, srs, cols, rows):
            """rows: (geometry_blob, coordinates, *attribute values); `coordinates` is every (x, y) of the geometry, used for the layer's extent."""
            ddl = ", ".join(f"{c} {t}" for c, t in cols)
            db.execute(f"CREATE TABLE {name} (fid INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, geom {gtype}, {ddl})")
            db.executemany(f"INSERT INTO {name} (geom, {', '.join(c for c, _ in cols)}) VALUES (?{',?' * len(cols)})",  # noqa: S608
                           [(r[0], *r[2:]) for r in rows])
            xs = [x for r in rows for x, _y in r[1]]
            ys = [y for r in rows for _x, y in r[1]]
            db.execute("INSERT INTO gpkg_contents VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (name, "features", name, "", STAMP, min(xs), min(ys), max(xs), max(ys), srs))
            db.execute("INSERT INTO gpkg_geometry_columns VALUES (?,?,?,?,0,0)", (name, "geom", gtype, srs))

        layer("smoke_roads", "LINESTRING", 32636,
              [("osm_id", "INTEGER"), ("name", "TEXT"), ("highway", "TEXT"), ("oneway", "TEXT"), ("speed_kmh", "REAL")],
              [(line(32636, g), g, i, n, h, o, sp) for i, n, h, o, sp, g in roads()])
        layer("smoke_facilities", "POINT", 32636, [("name", "TEXT"), ("type", "TEXT")],
              [(point(32636, x, y), [(x, y)], n, t) for n, t, x, y in FACILITIES])
        layer("smoke_admin_dup", "POLYGON", 32636, [("admin_name", "TEXT"), ("population", "INTEGER"), ("need", "INTEGER")],
              [(polygon(32636, c), c, n, p, d) for n, p, d, c in ADMIN_DUP])
        wgs = [(n, utm36_to_lonlat(x, y)) for n, x, y in pts]
        layer("smoke_points_4326", "POINT", 4326, [("name", "TEXT")], [(point(4326, *xy), [xy], n) for n, xy in wgs])
        wgs = [(n, utm36_to_lonlat(x, y)) for n, x, y in hubs]
        layer("smoke_hubs_4326", "POINT", 4326, [("name", "TEXT")], [(point(4326, *xy), [xy], n) for n, xy in wgs])
        road, inside, beside = ubend_geometry()
        layer("smoke_ubend_road", "LINESTRING", 32636, [("name", "TEXT")], [(line(32636, road), road, "U road")])
        layer("smoke_ubend_facilities", "POINT", 32636, [("name", "TEXT")],
              [(point(32636, *inside), [inside], "Inside_the_U"), (point(32636, *beside), [beside], "Beside_the_arm")])
        db.commit()
    with sqlite3.connect(path) as db:
        db.execute("VACUUM")


def _dump(path):
    """The logical content (schema and rows), so the check does not depend on the SQLite version that wrote the file."""
    with sqlite3.connect(path) as db:
        return list(db.iterdump())


def selftest():
    """The projection maths must round-trip, and a known point must land where it should (Amman area, about 35.93 E 31.95 N)."""
    lon, lat = utm36_to_lonlat(777000.0, 3539000.0)
    x, y = lonlat_to_utm36(lon, lat)
    x0, y0 = lonlat_to_utm36(33.0, 0.0)
    # one degree east of the central meridian on the equator: 111319.49 m of arc, +5.65 m of Transverse Mercator stretch, times 0.9996
    east_1deg = lonlat_to_utm36(34.0, 0.0)[0] - 500000.0 - (111319.49 + 5.65) * 0.9996
    checks = [(35.9 < lon < 35.96 and 31.9 < lat < 32.0, f"smoke area maps to {lon}, {lat}"),
              (abs(x - 777000.0) < 0.001 and abs(y - 3539000.0) < 0.001, f"round trip gave {x}, {y}"),
              (abs(x0 - 500000.0) < 1e-6 and abs(y0) < 1e-6, "the central meridian is not at 500000"),
              (abs(east_1deg) < 1.0, f"one degree east is off by {east_1deg} m")]
    for ok, why in checks:
        if not ok:
            raise SystemExit("projection self-test failed: " + why)


def main():
    selftest()
    if "--check" in sys.argv:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d) / "smoke_network.gpkg"
            write(tmp)
            same = OUT.is_file() and _dump(OUT) == _dump(tmp)
        print("smoke_network.gpkg is up to date" if same else "smoke_network.gpkg differs from the generator: run tools/make_smoke_network.py")
        return 0 if same else 1
    write(OUT)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
