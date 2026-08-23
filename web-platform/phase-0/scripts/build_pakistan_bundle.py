from __future__ import annotations

import datetime as dt
import json
import pathlib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1] / "data" / "pakistan"
ROOT.mkdir(parents=True, exist_ok=True)

DATASETS = {
    "ocha-global-humanitarian-operational-presence-who-what-where-3w-portal": lambda rs: next(r for r in rs if r.get("name") == "global-3w-2023-06-08.xlsx"),
    "cod-ab-pak": lambda rs: next(r for r in rs if r.get("format") == "GeoJSON"),
    "cod-ps-pak": lambda rs: next(r for r in rs if r.get("name") == "pak_admpop_adm2_v2.csv"),
    "pakistan-healthsites": lambda rs: next(r for r in rs if r.get("name") == "pakistan-healthsites-csv"),
    "hotosm_pak_roads": lambda rs: next(r for r in rs if r.get("format") == "GeoJSON" and "polygons" in r.get("name", "")),
    "pakistan-humanitarian-needs-overview": lambda rs: rs[0],
    "pak-flood-fl-20250829-pak-00": lambda rs: rs[0],
}


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def main() -> None:
    manifest = {
        "retrieved_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "country": "Pakistan",
        "sources": [],
    }
    for dataset_id, selector in DATASETS.items():
        package = get_json(
            "https://data.humdata.org/api/3/action/package_show?id=" + dataset_id
        )["result"]
        resource = selector(package.get("resources", []))
        filename = resource["name"].replace("/", "_")
        destination = ROOT / filename
        print(f"Downloading {dataset_id}: {filename}")
        with urllib.request.urlopen(resource["url"], timeout=300) as response:
            payload = response.read()
        destination.write_bytes(payload)
        manifest["sources"].append(
            {
                "dataset_id": dataset_id,
                "dataset_title": package.get("title"),
                "metadata_modified": package.get("metadata_modified"),
                "resource_name": resource.get("name"),
                "format": resource.get("format"),
                "size": len(payload),
                "url": resource.get("url"),
                "local_file": str(destination.relative_to(ROOT)),
                "notes": (package.get("notes") or "")[:500],
            }
        )
        print(f"Saved {destination} ({len(payload)} bytes)")
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Manifest sources: {len(manifest['sources'])}")


if __name__ == "__main__":
    main()
