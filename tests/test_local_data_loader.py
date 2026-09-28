# -*- coding: utf-8 -*-
"""agent/local_data_loader.py's background-thread half (no QGIS needed): region lookup, the
download itself, reuse of a recent copy, and unzipping only what's needed."""
import io
import json
import os
import shutil
import tempfile
import time
import unittest
import zipfile
from unittest.mock import MagicMock, patch

from cartogen_ai.core.agent import local_data_loader as ldl

REGION = {"id": "jordan", "name": "Jordan",
          "shp_url": "https://download.geofabrik.de/asia/jordan-latest-free.shp.zip", "size_bytes": 0}


def _zip_bytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for stem in ("gis_osm_roads_free_1", "gis_osm_pois_free_1", "gis_osm_pois_a_free_1",
                     "gis_osm_buildings_a_free_1"):
            for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
                z.writestr(stem + ext, b"x")
        z.writestr("README", b"readme")
    return buf.getvalue()


def _response(body, headers=None):
    r = MagicMock()
    stream = io.BytesIO(body)
    r.read.side_effect = lambda n=-1: stream.read(n)
    r.headers = headers or {"Content-Length": str(len(body))}
    r.__enter__.return_value = r
    return r


class _TmpDir(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="cg_localdata_")
        self.addCleanup(shutil.rmtree, self.dir, True)


class TestDownload(_TmpDir):
    def test_downloads_streams_and_keeps_only_a_finished_zip(self):
        body = _zip_bytes()
        seen = []
        with patch("urllib.request.urlopen", return_value=_response(body)):
            path = ldl.download_extract(REGION, self.dir, progress=seen.append)
        self.assertTrue(zipfile.is_zipfile(path))
        self.assertTrue(path.endswith("jordan-latest-free.shp.zip"))
        self.assertFalse(os.path.exists(path + ".part"))
        self.assertEqual(seen[-1], 100.0)

    def test_a_recent_copy_is_reused_without_a_request(self):
        path = os.path.join(self.dir, "jordan-latest-free.shp.zip")
        with open(path, "wb") as f:
            f.write(_zip_bytes())
        with patch("urllib.request.urlopen") as mock_open:
            self.assertEqual(ldl.download_extract(REGION, self.dir), path)
        mock_open.assert_not_called()

    def test_a_stale_copy_is_downloaded_again(self):
        path = os.path.join(self.dir, "jordan-latest-free.shp.zip")
        with open(path, "wb") as f:
            f.write(_zip_bytes())
        old = time.time() - ldl.EXTRACT_MAX_AGE_S - 60
        os.utime(path, (old, old))
        with patch("urllib.request.urlopen", return_value=_response(_zip_bytes())) as mock_open:
            ldl.download_extract(REGION, self.dir)
        mock_open.assert_called_once()

    def test_an_error_page_is_not_kept_as_the_extract(self):
        with patch("urllib.request.urlopen", return_value=_response(b"<html>error</html>")):
            with self.assertRaises(ValueError):
                ldl.download_extract(REGION, self.dir)
        self.assertEqual(os.listdir(self.dir), [])

    def test_cancelling_stops_and_leaves_no_zip(self):
        with patch("urllib.request.urlopen", return_value=_response(_zip_bytes())):
            with self.assertRaises(InterruptedError):
                ldl.download_extract(REGION, self.dir, is_cancelled=lambda: True)
        self.assertFalse(any(n.endswith(".zip") for n in os.listdir(self.dir)))


class TestExtract(_TmpDir):
    def test_only_roads_and_pois_are_unzipped(self):
        zpath = os.path.join(self.dir, "x.zip")
        with open(zpath, "wb") as f:
            f.write(_zip_bytes())
        found = ldl.extract_members(zpath, os.path.join(self.dir, "out"))
        self.assertEqual(set(found), set(ldl.MEMBERS))
        names = os.listdir(os.path.join(self.dir, "out"))
        self.assertIn("gis_osm_roads_free_1.dbf", names)  # sidecars come along
        self.assertFalse(any("buildings" in n for n in names))
        self.assertNotIn("README", names)


class TestResolveRegion(_TmpDir):
    INDEX = {"features": [{"type": "Feature",
                           "properties": {"id": "jordan", "name": "Jordan", "iso3166-1:alpha2": ["JO"],
                                          "urls": {"shp": REGION["shp_url"]}},
                           "geometry": {"type": "Polygon",
                                        "coordinates": [[[35, 29], [39, 29], [39, 33], [35, 33], [35, 29]]]}}]}

    def test_finds_the_region_and_its_size_and_caches_the_index(self):
        index = _response(json.dumps(self.INDEX).encode())
        head = _response(b"", {"Content-Length": "60123456"})
        with patch("urllib.request.urlopen", side_effect=[index, head]):
            r = ldl.resolve_region(35.93, 31.95, self.dir)
        self.assertEqual((r["id"], r["size_bytes"]), ("jordan", 60123456))
        self.assertTrue(os.path.exists(os.path.join(self.dir, "geofabrik-index-v1.json")))
        with patch("urllib.request.urlopen", side_effect=[_response(b"", {"Content-Length": "1"})]) as m:
            ldl.resolve_region(35.93, 31.95, self.dir)  # index comes from the cache now
        self.assertEqual(m.call_count, 1)

    def test_no_region_is_a_clear_error(self):
        with patch("urllib.request.urlopen", return_value=_response(json.dumps(self.INDEX).encode())):
            r = ldl.resolve_region(-30.0, 30.0, self.dir)
        self.assertIn("No Geofabrik extract covers this location", r["error"])

    def test_a_broken_index_is_not_cached(self):
        with patch("urllib.request.urlopen", return_value=_response(b"<html>busy</html>")), \
             patch("cartogen_ai.core.agent.tools._urllib_retry.time.sleep"):
            r = ldl.resolve_region(35.93, 31.95, self.dir)
        self.assertIn("region list", r["error"])
        self.assertFalse(os.path.exists(os.path.join(self.dir, "geofabrik-index-v1.json")))


class TestQueryPointWgs84(unittest.TestCase):
    """Live-reported, 2026-09-28: the local-data download offer picked its target region from
    the QGIS canvas's current view centre, not the coordinate the request itself named --
    wrong whenever the canvas hadn't been panned there yet. This is the CRS-reprojection half
    of the fix; see test_local_data_sources.py's TestExtractCoordinatePair for the text-parsing
    half. The full reprojection path needs real QGIS classes (QgsCoordinateTransform etc.),
    live-QGIS-only like canvas_center_wgs84 right above it -- these two branches are QGIS-free
    and run on the plain `test` CI job."""

    def test_no_coordinate_in_text_returns_none_without_touching_qgis(self):
        with patch.object(ldl, "QGIS_AVAILABLE", True):
            self.assertIsNone(ldl.query_point_wgs84("Buffer 5 km around active GDACS alerts"))

    def test_qgis_unavailable_returns_none_even_with_a_coordinate_in_text(self):
        with patch.object(ldl, "QGIS_AVAILABLE", False):
            self.assertIsNone(ldl.query_point_wgs84(
                "Health facilities beyond one hour's travel 3999770.2,3743455.7"))


if __name__ == "__main__":
    unittest.main()
