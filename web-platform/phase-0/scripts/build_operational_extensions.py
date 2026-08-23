from __future__ import annotations

import datetime as dt
import json
import pathlib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1] / "data" / "extensions"
ROOT.mkdir(parents=True, exist_ok=True)

SOURCES = [
    ("pakistan-acled-conflict-data", "pakistan_political_violence_events_and_fatalities_by_month-year", "xlsx"),
    ("world-bank-infrastructure-indicators-for-pakistan", "Infrastructure Indicators for Pakistan", "csv"),
    ("pakistan-accessibility-indicators", "PAK_education_access_long.csv", "csv"),
    ("pakistan-accessibility-indicators", "PAK_hospitals_access_long.csv", "csv"),
    ("pakistan-accessibility-indicators", "PAK_primary_healthcare_access_long.csv", "csv"),
    ("ourairports-pak", "List of airports in Pakistan (no HXL tags)", "csv"),
    ("afghanistan-operational-presence", "afghanistan-3w-operational-presence-january-march-2026.csv", "csv"),
    ("afghanistan-operational-presence", "afghanistan-3w-operational-capacity-january-march-2026.csv", "csv"),
]


def package(dataset_id: str) -> dict:
    url = "https://data.humdata.org/api/3/action/package_show?id=" + dataset_id
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)["result"]


def main() -> None:
    manifest = {
        "retrieved_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "sources": [],
    }
    for dataset_id, resource_name, expected_format in SOURCES:
        pkg = package(dataset_id)
        candidates = [r for r in pkg.get("resources", []) if r.get("name") == resource_name]
        if not candidates:
            raise RuntimeError(f"Resource not found: {dataset_id} / {resource_name}")
        resource = candidates[0]
        filename = resource_name.replace("/", "_")
        destination = ROOT / filename
        print(f"Downloading {dataset_id}: {filename}")
        with urllib.request.urlopen(resource["url"], timeout=300) as response:
            payload = response.read()
        destination.write_bytes(payload)
        manifest["sources"].append(
            {
                "dataset_id": dataset_id,
                "dataset_title": pkg.get("title"),
                "metadata_modified": pkg.get("metadata_modified"),
                "license": pkg.get("license_title"),
                "resource_name": resource_name,
                "format": resource.get("format", expected_format),
                "size": len(payload),
                "url": resource.get("url"),
                "local_file": str(destination.relative_to(ROOT)),
            }
        )
        print(f"Saved {destination} ({len(payload)} bytes)")
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Manifest sources: {len(manifest['sources'])}")


if __name__ == "__main__":
    main()
