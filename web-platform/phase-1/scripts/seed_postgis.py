#!/usr/bin/env python3
"""Seed the Phase 1 demo project with real Pakistan boundary and facility data.

The loader is intentionally explicit: it reads phase-0/data/pakistan, builds one
transactional SQL payload, and executes it through the running PostGIS compose
service. It is safe to re-run because seeded layers are replaced by source key.
"""
from __future__ import annotations

import csv
import json
import pathlib
import subprocess
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT.parent / "phase-0" / "data" / "pakistan"
PROJECT_ID = "pakistan-humanitarian-screening"
ORG_ID = "demo-humanitarian-lab"

def sql_text(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"

def geojson_from_zip(path: pathlib.Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith((".geojson", ".json"))]
        if not names:
            raise RuntimeError(f"No GeoJSON member in {path.name}")
        return json.loads(archive.read(names[0]).decode("utf-8"))

def facilities(path: pathlib.Path) -> dict:
    features = []
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                x, y = float(row["X"]), float(row["Y"])
            except (KeyError, TypeError, ValueError):
                continue
            properties = {k: v for k, v in row.items() if k not in {"X", "Y"} and v not in (None, "")}
            features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [x, y]}, "properties": properties})
    return {"type": "FeatureCollection", "features": features}

def layer_sql(name: str, source: str, licence: str, metadata: dict, collection: dict) -> str:
    payload = json.dumps(collection["features"], ensure_ascii=False, separators=(",", ":"))
    metadata_json = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
    return f"""
DELETE FROM project_layers WHERE project_id={sql_text(PROJECT_ID)} AND organization_id={sql_text(ORG_ID)} AND source_resource={sql_text(source)};
WITH layer AS (
  INSERT INTO project_layers (project_id, organization_id, name, source_resource, licence, metadata)
  VALUES ({sql_text(PROJECT_ID)}, {sql_text(ORG_ID)}, {sql_text(name)}, {sql_text(source)}, {sql_text(licence)}, {sql_text(metadata_json)}::jsonb)
  RETURNING id
)
INSERT INTO project_layer_features (layer_id, project_id, organization_id, geometry, properties)
SELECT layer.id, {sql_text(PROJECT_ID)}, {sql_text(ORG_ID)},
       ST_SetSRID(ST_GeomFromGeoJSON(feature->'geometry'), 4326),
       COALESCE(feature->'properties', '{{}}'::jsonb)
FROM layer CROSS JOIN jsonb_array_elements({sql_text(payload)}::jsonb) AS feature;
"""

def main() -> int:
    boundary = geojson_from_zip(DATA / "pak_admin_boundaries.geojson.zip")
    health = facilities(DATA / "pakistan-healthsites-csv")
    sql = f"""
BEGIN;
INSERT INTO projects (id, organization_id, name, sector, crs, status, metadata)
VALUES ({sql_text(PROJECT_ID)}, {sql_text(ORG_ID)}, 'Pakistan Humanitarian Service Coverage', 'Humanitarian aid', 'EPSG:4326', 'active', '{{"seeded":true,"source":"phase-0/data/pakistan"}}'::jsonb)
ON CONFLICT (id) DO UPDATE SET organization_id=EXCLUDED.organization_id, updated_at=now();
{layer_sql('Pakistan administrative boundaries', 'seed:pak_admin_boundaries.geojson', 'Open Database License (ODbL)', {'seeded': True, 'source': 'phase-0/data/pakistan/pak_admin_boundaries.geojson.zip'}, boundary)}
{layer_sql('Pakistan health facilities', 'seed:pakistan-healthsites-csv', 'OpenStreetMap contributors', {'seeded': True, 'source': 'phase-0/data/pakistan/pakistan-healthsites-csv'}, health)}
COMMIT;
"""
    command = ["docker", "compose", "exec", "-T", "postgis", "psql", "-U", "cartogen", "-d", "cartogen_phase1", "-v", "ON_ERROR_STOP=1"]
    result = subprocess.run(command, input=sql, text=True, cwd=ROOT, capture_output=True)
    if result.returncode:
        sys.stderr.write(result.stderr)
        return result.returncode
    print(json.dumps({"project": PROJECT_ID, "layers": 2, "boundary_features": len(boundary.get("features", [])), "facility_features": len(health.get("features", []))}))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
