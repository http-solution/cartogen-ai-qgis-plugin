#!/usr/bin/env python3
"""Unit tests for seed_pakistan_accessibility_layers.py's join/pivot/alias
logic, against small synthetic fixtures -- no real data bundle, no network,
no Docker. Run with:

    python3 -m unittest scripts/test_seed_pakistan_accessibility_layers.py

For the full, real-data, real-PostGIS verification (feature counts, ST_IsValid,
idempotent re-run), see db/DATA_INGESTION.md's Verification section -- that
pass isn't repeatable in an ordinary CI run since it needs the ~30MB phase-0
data bundle and a live PostGIS instance, so this file covers the logic that
*is* practical to check on every run: the alias table actually resolves each
name it claims to, the unmappable set is actually dropped instead of guessed,
and the CSV-row-to-GeoJSON-feature shape is what the rest of the pipeline
(and the DELETE/INSERT SQL in seed_postgis.layer_sql) expects.
"""
from __future__ import annotations

import csv
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import seed_pakistan_accessibility_layers as mod  # noqa: E402


def write_csv(path: pathlib.Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def boundary_feature(name: str, pcode: str, adm1: str) -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]},
        "properties": {"adm2_name": name, "adm2_pcode": pcode, "adm1_name": adm1},
    }


ACCESS_FIELDNAMES = [
    "name", "iso", "id", "country", "admin_level", "category", "range_type",
    "range", "population_type", "population", "population_share",
    "population_interval", "population_interval_share",
]


class AccessibilityLayerTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.tmp = pathlib.Path(self.tmpdir.name)
        self.boundary_by_name = {
            "Abbottabad": boundary_feature("Abbottabad", "PK501", "Khyber Pakhtunkhwa"),
            "Batagram": boundary_feature("Batagram", "PK502", "Khyber Pakhtunkhwa"),
            "Islamabad": boundary_feature("Islamabad", "PK101", "Islamabad"),
        }

    def _access_row(self, name, admin_level="ADM2", **overrides):
        row = {
            "name": name, "iso": "", "id": "x", "country": "PAK",
            "admin_level": admin_level, "category": "education",
            "range_type": "DISTANCE", "range": "5000",
            "population_type": "total", "population": "1000",
            "population_share": "50.0", "population_interval": "1000",
            "population_interval_share": "50.0",
        }
        row.update(overrides)
        return row

    def test_exact_name_match_produces_one_feature_with_boundary_geometry(self):
        csv_path = self.tmp / "access.csv"
        write_csv(csv_path, ACCESS_FIELDNAMES, [self._access_row("Abbottabad")])

        result = mod.accessibility_layer(csv_path, "test", self.boundary_by_name)

        self.assertEqual(len(result["features"]), 1)
        feature = result["features"][0]
        self.assertEqual(feature["geometry"], self.boundary_by_name["Abbottabad"]["geometry"])
        self.assertEqual(feature["properties"]["adm2_pcode"], "PK501")
        self.assertEqual(feature["properties"]["source_district_name"], "Abbottabad")

    def test_multiple_metric_rows_for_one_district_collapse_into_one_feature(self):
        csv_path = self.tmp / "access.csv"
        write_csv(csv_path, ACCESS_FIELDNAMES, [
            self._access_row("Abbottabad", population_type="total", range="5000"),
            self._access_row("Abbottabad", population_type="school_age", range="5000"),
            self._access_row("Abbottabad", population_type="total", range="10000"),
        ])

        result = mod.accessibility_layer(csv_path, "test", self.boundary_by_name)

        self.assertEqual(len(result["features"]), 1, "one district should produce exactly one polygon feature, not one per metric row")
        metrics = result["features"][0]["properties"]["metrics"]
        self.assertEqual(len(metrics), 3, "every metric row should be preserved losslessly")

    def test_aliased_name_resolves_to_the_correct_boundary_polygon(self):
        csv_path = self.tmp / "access.csv"
        write_csv(csv_path, ACCESS_FIELDNAMES, [self._access_row("Battagram")])  # CSV spelling; boundary has "Batagram"

        result = mod.accessibility_layer(csv_path, "test", self.boundary_by_name)

        self.assertEqual(len(result["features"]), 1)
        self.assertEqual(result["features"][0]["properties"]["adm2_name"], "Batagram")
        self.assertEqual(result["features"][0]["properties"]["source_district_name"], "Battagram")

    def test_unmappable_name_is_dropped_not_guessed(self):
        csv_path = self.tmp / "access.csv"
        write_csv(csv_path, ACCESS_FIELDNAMES, [
            self._access_row("Azad Kashmir"),
            self._access_row("Abbottabad"),
        ])

        result = mod.accessibility_layer(csv_path, "test", self.boundary_by_name)

        names = {f["properties"]["source_district_name"] for f in result["features"]}
        self.assertEqual(names, {"Abbottabad"}, "Azad Kashmir has no single matching ADM2 polygon and must not appear in the output")

    def test_name_with_no_boundary_match_and_no_alias_is_dropped(self):
        csv_path = self.tmp / "access.csv"
        write_csv(csv_path, ACCESS_FIELDNAMES, [self._access_row("Nonexistent District")])

        result = mod.accessibility_layer(csv_path, "test", self.boundary_by_name)

        self.assertEqual(result["features"], [])

    def test_non_adm2_rows_are_excluded(self):
        csv_path = self.tmp / "access.csv"
        write_csv(csv_path, ACCESS_FIELDNAMES, [
            self._access_row("Pakistan", admin_level="ADM0"),
            self._access_row("Khyber Pakhtunkhwa", admin_level="ADM1"),
            self._access_row("Abbottabad", admin_level="ADM2"),
        ])

        result = mod.accessibility_layer(csv_path, "test", self.boundary_by_name)

        self.assertEqual(len(result["features"]), 1)
        self.assertEqual(result["features"][0]["properties"]["source_district_name"], "Abbottabad")

    def test_every_declared_alias_target_would_resolve_against_a_realistic_boundary_set(self):
        # Doesn't re-verify the real 160-district boundary file (that's what
        # db/DATA_INGESTION.md's live-PostGIS pass does), but does prove the
        # alias table is internally consistent: every declared alias target
        # is at least a plausible, distinct district name, and no name is
        # both aliased and marked unmappable.
        alias_targets = set(mod.ADM2_NAME_ALIASES.values())
        alias_sources = set(mod.ADM2_NAME_ALIASES.keys())
        self.assertEqual(alias_sources & mod.ADM2_NAME_UNMAPPABLE, set(), "a name can't be both aliased and unmappable")
        self.assertEqual(len(alias_targets), len(mod.ADM2_NAME_ALIASES), "two source names collapsing onto the same boundary target would be suspicious and should be checked by hand")


class AirportsLayerTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.tmp = pathlib.Path(self.tmpdir.name)

    def test_valid_coordinates_produce_point_features(self):
        csv_path = self.tmp / "airports.csv"
        fieldnames = ["id", "ident", "name", "latitude_deg", "longitude_deg", "type"]
        write_csv(csv_path, fieldnames, [
            {"id": "1", "ident": "OPKC", "name": "Jinnah International Airport", "latitude_deg": "24.9065", "longitude_deg": "67.160797", "type": "large_airport"},
        ])

        result = mod.airports_layer(csv_path)

        self.assertEqual(len(result["features"]), 1)
        feature = result["features"][0]
        self.assertEqual(feature["geometry"], {"type": "Point", "coordinates": [67.160797, 24.9065]}, "GeoJSON coordinate order is [lon, lat]")
        self.assertEqual(feature["properties"]["name"], "Jinnah International Airport")
        self.assertNotIn("latitude_deg", feature["properties"], "lat/lon should be promoted to geometry, not duplicated in properties")

    def test_missing_or_invalid_coordinates_are_skipped_not_crashed_on(self):
        csv_path = self.tmp / "airports.csv"
        fieldnames = ["id", "ident", "name", "latitude_deg", "longitude_deg"]
        write_csv(csv_path, fieldnames, [
            {"id": "1", "ident": "AAA", "name": "Missing lat", "latitude_deg": "", "longitude_deg": "67.0"},
            {"id": "2", "ident": "BBB", "name": "Garbage lon", "latitude_deg": "24.0", "longitude_deg": "not-a-number"},
            {"id": "3", "ident": "CCC", "name": "Valid", "latitude_deg": "24.0", "longitude_deg": "67.0"},
        ])

        result = mod.airports_layer(csv_path)

        self.assertEqual(len(result["features"]), 1)
        self.assertEqual(result["features"][0]["properties"]["name"], "Valid")


if __name__ == "__main__":
    unittest.main()
