from __future__ import annotations

import csv
import json
import pathlib
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT.parent / "phase-0" / "data"
PAK = DATA / "pakistan"
EXT = DATA / "extensions"
OUT = ROOT / "demo-data.json"


def read_csv(path: pathlib.Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
        return list(csv.DictReader(handle))


def source_row(manifest: dict, local_file: str) -> dict:
    for item in manifest["sources"]:
        if item["local_file"] == local_file:
            return item
    raise KeyError(local_file)


def main() -> None:
    pak_manifest = json.loads((PAK / "manifest.json").read_text(encoding="utf-8"))
    ext_manifest = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
    w3 = read_csv(PAK / "global-3w-pakistan-2023-06-08.csv")
    pop = read_csv(PAK / "pak_admpop_adm2_v2.csv")
    health = read_csv(PAK / "pakistan-healthsites-csv")
    education = read_csv(EXT / "PAK_education_access_long.csv")
    hospitals = read_csv(EXT / "PAK_hospitals_access_long.csv")
    primary = read_csv(EXT / "PAK_primary_healthcare_access_long.csv")
    airports = read_csv(EXT / "List of airports in Pakistan (no HXL tags)")
    infra = read_csv(EXT / "Infrastructure Indicators for Pakistan")
    sectors = Counter(row.get("sector", "").strip() for row in w3)
    org_types = Counter(row.get("type", "").strip() for row in w3)
    demo = {
        "project": {
            "id": "pakistan-humanitarian-screening",
            "name": "Pakistan Humanitarian Service Coverage",
            "sector": "Humanitarian aid",
            "status": "Phase 1 data-backed vertical slice",
            "crs": "EPSG:4326",
            "lastRefreshed": pak_manifest["retrieved_at"],
        },
        "summary": {
            "presenceRecords": len(w3),
            "distinctOrganizations": len({r.get("organization", "").strip() for r in w3 if r.get("organization", "").strip()}),
            "populationAdmin2Rows": len(pop),
            "healthFacilities": len(health),
            "educationAccessRows": len(education),
            "hospitalAccessRows": len(hospitals),
            "primaryHealthcareAccessRows": len(primary),
            "airports": len(airports),
            "infrastructureIndicators": len(infra),
        },
        "presence": {
            "sectors": sectors.most_common(12),
            "organizationTypes": org_types.most_common(),
            "sample": w3[:12],
        },
        "sources": [
            source_row(pak_manifest, "global-3w-2023-06-08.xlsx"),
            source_row(pak_manifest, "pak_admin_boundaries.geojson.zip"),
            source_row(pak_manifest, "pak_admpop_adm2_v2.csv"),
            source_row(pak_manifest, "pakistan-healthsites-csv"),
            source_row(pak_manifest, "hotosm_pak_roads_polygons_geojson.zip"),
            source_row(pak_manifest, "PAK_HNO_2021.xlsx"),
            source_row(pak_manifest, "pak_wfpadam_flood_20250829.zip"),
            *[source_row(ext_manifest, name) for name in [
                "pakistan_political_violence_events_and_fatalities_by_month-year",
                "Infrastructure Indicators for Pakistan",
                "PAK_education_access_long.csv",
                "PAK_hospitals_access_long.csv",
                "PAK_primary_healthcare_access_long.csv",
                "List of airports in Pakistan (no HXL tags)",
            ]],
        ],
        "analysis": {
            "title": "Humanitarian service coverage screening",
            "question": "Which areas combine population and needs context with low reported partner presence and weak service accessibility?",
            "steps": [
                {"id": 1, "label": "Normalize sources", "status": "complete", "detail": "Dates, source metadata, and identifiers are recorded."},
                {"id": 2, "label": "Review compatibility", "status": "warning", "detail": "Population reference year 2017 does not directly match the newer boundary vintage."},
                {"id": 3, "label": "Aggregate presence", "status": "complete", "detail": f"{len(w3)} Pakistan 3W records are available for sector filtering."},
                {"id": 4, "label": "Compare accessibility", "status": "ready", "detail": "Education, hospital, and primary-healthcare access tables are loaded."},
                {"id": 5, "label": "Generate review output", "status": "review", "detail": "Human confirmation is required before treating a screening result as an operational decision."},
            ],
        },
    }
    OUT.write_text(json.dumps(demo, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT} sources={len(demo['sources'])} presence={len(w3)}")


if __name__ == "__main__":
    main()
