#!/usr/bin/env python3
"""Seed the remaining Docker-independent, genuinely-spatial Pakistan layers
into PostGIS: ADM2-level education/hospital/primary-healthcare accessibility,
airports, and roads.

This extends seed_postgis.py's boundary+health-facility seed with the rest of
phase-0/data that (a) actually carries a geometry, or can be joined to one
without fabricating anything, and (b) is licensed for redistribution. See
db/DATA_INGESTION.md for the full account of what's included here, what's
deliberately left out (the 3W presence roster and the World Bank
infrastructure indicators are both non-spatial national/nationwide tables
with no sub-national geometry to join against; the ACLED conflict/political
violence dataset is both non-spatial -- country-level monthly totals only --
and carries a Terms of Use that prohibits redistributing ACLED's raw data,
which loading it into a queryable, exportable project layer would do), and
why.

Like seed_postgis.py, this is safe to re-run: each layer is replaced by its
source key (DELETE + re-INSERT in the same transaction as everything else).
Run this after seed_postgis.py, against the same running PostGIS compose
service.
"""
from __future__ import annotations

import csv
import json
import pathlib
import subprocess
import sys
import zipfile
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA0 = ROOT.parent / "phase-0" / "data"
PAK = DATA0 / "pakistan"
EXT = DATA0 / "extensions"
PROJECT_ID = "pakistan-humanitarian-screening"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from seed_postgis import sql_text, layer_sql  # noqa: E402 -- reuse the existing SQL builders (same PROJECT_ID/ORG_ID)

# Districts whose accessibility-CSV spelling differs from the boundary
# dataset's adm2_name but refer to the exact same single ADM2 district
# (verified by manual cross-check of every non-exact-match name against
# pak_admin2.geojson's adm2_name list -- see db/DATA_INGESTION.md for the
# full comparison). Key = name as it appears in the *_access_long.csv files,
# value = matching pak_admin2.geojson adm2_name.
ADM2_NAME_ALIASES = {
    "Battagram": "Batagram",
    "Dera Ismail Khan": "D. I. Khan",
    "Diamer": "Diamir",
    "Islamabad Capital Territory": "Islamabad",
    "Jafarabad": "Jaffarabad",
    "Layyah": "Leiah",
    "Mirpurkhas": "Mirpur Khas",
    "Naushehro Feroze": "Naushahro Feroze",
    "Nawabshah": "Shaheed Benazir Abad",
    "Qambar Shahdadkot": "Kambar Shahdad Kot",
    "Qilla Abdullah": "Killa Abdullah",
    "Qilla Saifullah": "Killa Saifullah",
    "Sheikhpura": "Sheikhupura",
    "Umerkot": "Umer Kot",
    "Vihari": "Vehari",
}

# Names in the accessibility CSVs that do NOT correspond to exactly one ADM2
# polygon, so there is no correct single match to attach them to -- dropped
# rather than guessed:
#   - "Azad Kashmir" is tagged admin_level=ADM2 in the source but is really
#     the whole AJK region, covering 10 separate ADM2 polygons (Bagh,
#     Bhimber, Haveli, Jhelum Valley, Kotli, Mirpur, Muzaffarabad, Neelum,
#     Poonch, Sudhnoti).
#   - "Chitral" was split into "Chitral Lower" / "Chitral Upper".
#   - "Karachi" is split into 6 ADM2 polygons (Central/East/Korangi/Malir/
#     South/West Karachi).
#   - "Kohistan" is split into "Kohistan Lower" / "Kohistan Upper" /
#     "Kolai Palas Kohistan".
ADM2_NAME_UNMAPPABLE = {"Azad Kashmir", "Chitral", "Karachi", "Kohistan"}

ACCESSIBILITY_LICENCE = "Creative Commons Attribution Share-Alike (CC BY-SA) - HeiGIT / HOT"


def read_csv(path: pathlib.Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
        return list(csv.DictReader(handle))


def load_admin2_boundaries() -> dict[str, dict]:
    with zipfile.ZipFile(PAK / "pak_admin_boundaries.geojson.zip") as archive:
        data = json.loads(archive.read("pak_admin2.geojson"))
    return {feature["properties"]["adm2_name"]: feature for feature in data["features"]}


def accessibility_layer(csv_path: pathlib.Path, label: str, boundary_by_name: dict[str, dict]) -> dict:
    """Pivot a *_access_long.csv (one row per district x population-type x
    range) into one GeoJSON feature per ADM2 district, geometry from the
    boundary dataset, with every metric row for that district preserved as a
    properties.metrics array -- lossless, and one polygon per district
    rather than duplicate overlapping polygons per metric row.

    csv_path is a full path (not just a filename under EXT) so this is
    testable against small synthetic fixtures -- see
    test_seed_pakistan_accessibility_layers.py."""
    rows = [row for row in read_csv(csv_path) if row.get("admin_level") == "ADM2"]
    by_district: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_district[row["name"]].append(row)

    features = []
    dropped_unmapped = set()
    dropped_no_match = set()
    for district_name, metric_rows in by_district.items():
        if district_name in ADM2_NAME_UNMAPPABLE:
            dropped_unmapped.add(district_name)
            continue
        boundary_name = ADM2_NAME_ALIASES.get(district_name, district_name)
        boundary_feature = boundary_by_name.get(boundary_name)
        if boundary_feature is None:
            dropped_no_match.add(district_name)
            continue
        metrics = [
            {
                "category": row["category"],
                "range_type": row["range_type"],
                "range": row["range"],
                "population_type": row["population_type"],
                "population": row["population"],
                "population_share": row["population_share"],
            }
            for row in metric_rows
        ]
        boundary_props = boundary_feature["properties"]
        features.append({
            "type": "Feature",
            "geometry": boundary_feature["geometry"],
            "properties": {
                "adm2_name": boundary_props["adm2_name"],
                "adm2_pcode": boundary_props["adm2_pcode"],
                "adm1_name": boundary_props["adm1_name"],
                "source_district_name": district_name,
                "metrics": metrics,
            },
        })

    print(
        f"{label}: {len(features)} districts matched; "
        f"{len(dropped_unmapped)} dropped as ambiguous 1:many ({sorted(dropped_unmapped)}); "
        f"{len(dropped_no_match)} dropped with no boundary match ({sorted(dropped_no_match)})",
        file=sys.stderr,
    )
    return {"type": "FeatureCollection", "features": features}


def airports_layer(csv_path: pathlib.Path | None = None) -> dict:
    rows = read_csv(csv_path or EXT / "List of airports in Pakistan (no HXL tags)")
    features = []
    skipped = 0
    for row in rows:
        try:
            lat, lon = float(row["latitude_deg"]), float(row["longitude_deg"])
        except (KeyError, TypeError, ValueError):
            skipped += 1
            continue
        properties = {k: v for k, v in row.items() if k not in {"latitude_deg", "longitude_deg"} and v not in (None, "")}
        features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": properties})
    if skipped:
        print(f"airports: skipped {skipped} row(s) with missing/invalid coordinates", file=sys.stderr)
    return {"type": "FeatureCollection", "features": features}


def roads_layer() -> dict:
    with zipfile.ZipFile(PAK / "hotosm_pak_roads_polygons_geojson.zip") as archive:
        [member] = [name for name in archive.namelist() if name.lower().endswith(".geojson")]
        return json.loads(archive.read(member))


def build_layers() -> list[tuple[str, str, str, dict]]:
    boundary_by_name = load_admin2_boundaries()
    return [
        ("Pakistan education access (ADM2)", "seed:PAK_education_access_long.csv",
         ACCESSIBILITY_LICENCE, accessibility_layer(EXT / "PAK_education_access_long.csv", "education access", boundary_by_name)),
        ("Pakistan hospital access (ADM2)", "seed:PAK_hospitals_access_long.csv",
         ACCESSIBILITY_LICENCE, accessibility_layer(EXT / "PAK_hospitals_access_long.csv", "hospital access", boundary_by_name)),
        ("Pakistan primary healthcare access (ADM2)", "seed:PAK_primary_healthcare_access_long.csv",
         ACCESSIBILITY_LICENCE, accessibility_layer(EXT / "PAK_primary_healthcare_access_long.csv", "primary healthcare access", boundary_by_name)),
        ("Pakistan airports", "seed:pakistan-airports-ourairports",
         "Public Domain (OurAirports)", airports_layer()),
        ("Pakistan roads (OSM export)", "seed:hotosm_pak_roads_polygons_geojson.zip",
         "Open Database License (ODbL) - (c) OpenStreetMap contributors", roads_layer()),
    ]


def main() -> int:
    layers = build_layers()

    statements = ["BEGIN;"]
    for name, source, licence, collection in layers:
        statements.append(layer_sql(name, source, licence, {"seeded": True, "source": source}, collection))
    statements.append("COMMIT;")
    sql = "\n".join(statements)

    command = ["docker", "compose", "exec", "-T", "postgis", "psql", "-U", "cartogen", "-d", "cartogen_phase1", "-v", "ON_ERROR_STOP=1"]
    result = subprocess.run(command, input=sql, text=True, cwd=ROOT, capture_output=True)
    if result.returncode:
        sys.stderr.write(result.stderr)
        return result.returncode

    summary = {name: len(collection["features"]) for name, _, _, collection in layers}
    print(json.dumps({"project": PROJECT_ID, "layers": len(layers), "feature_counts": summary}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
