"""A boundary fetch that adds no layer must say so (owner's rc5 run, 2026-11-25: hand rows W2, W3 and C28 showed the boundary's source, licence and date and no layer, with no error).
The QGIS classes are replaced by fakes, so this runs without QGIS."""
import types
import unittest
from unittest.mock import patch

from cartogen_ai.core.agent.tools import humanitarian_tools as ht


class _Resp:
    def __init__(self, body):
        self.body = body

    def read(self, amt=-1):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_layer(valid):
    return types.SimpleNamespace(isValid=lambda: valid)


class TestGeoBoundariesNoFileLink(unittest.TestCase):
    def test_an_api_answer_with_no_file_link_is_an_error_and_is_not_remembered(self):
        api = b'{"boundaryName": "Yemen ADM1"}'
        ht._LOOKUP_CACHE.clear() if hasattr(ht._LOOKUP_CACHE, "clear") else None
        with patch.object(ht.urllib.request, "urlopen", return_value=_Resp(api)):
            first = ht.fetch_geoboundaries_network_phase("QQQ", "ADM1")
        self.assertIn("error", first)
        self.assertIn("gives no file to download", first["error"])
        self.assertIn("no layer was added", first["error"])
        self.assertNotIn("success", first)
        with patch.object(ht.urllib.request, "urlopen", return_value=_Resp(api)) as again:
            ht.fetch_geoboundaries_network_phase("QQQ", "ADM1")
        again.assert_called()                      # asked again: a retry may find the link, so the empty answer was not cached


class TestAddPhasesSayWhenNoLayerWasAdded(unittest.TestCase):
    def test_geoboundaries_without_a_downloaded_file_is_an_error(self):
        with patch.object(ht, "QGIS_AVAILABLE", True):
            res = ht.add_geoboundaries_layer_main_thread_phase({"success": True, "boundary": "Yemen ADM1", "download_url": "https://x", "iso3": "YEM", "admin_level": "ADM1"})
        self.assertIn("error", res)
        self.assertIn("no layer was added", res["error"])

    def test_geoboundaries_with_a_file_qgis_cannot_open_is_an_error(self):
        with patch.object(ht, "QGIS_AVAILABLE", True), patch.object(ht, "QgsVectorLayer", lambda *a, **k: _fake_layer(False), create=True):
            res = ht.add_geoboundaries_layer_main_thread_phase({"success": True, "local_path": "C:/x/y.geojson", "iso3": "YEM", "admin_level": "ADM1", "boundary": "b", "download_url": "u"})
        self.assertIn("error", res)
        self.assertIn("could not open it as a layer", res["error"])
        self.assertNotIn("success", res)

    def test_hdx_without_a_file_or_with_an_unreadable_file_is_an_error(self):
        with patch.object(ht, "QGIS_AVAILABLE", True):
            res = ht.add_hdx_admin_boundaries_layer_main_thread_phase({"success": True, "iso3": "YEM", "admin_level": "ADM1"})
        self.assertIn("error", res)
        with patch.object(ht, "QGIS_AVAILABLE", True), patch.object(ht, "QgsVectorLayer", lambda *a, **k: _fake_layer(False), create=True):
            res = ht.add_hdx_admin_boundaries_layer_main_thread_phase({"success": True, "local_path": "C:/x/y.geojson", "iso3": "YEM", "admin_level": "ADM1"})
        self.assertIn("could not open it as a layer", res["error"])

    def test_without_qgis_the_offline_behaviour_is_unchanged(self):
        with patch.object(ht, "QGIS_AVAILABLE", False):
            res = ht.add_geoboundaries_layer_main_thread_phase({"success": True, "boundary": "b", "download_url": "u", "iso3": "YEM", "admin_level": "ADM1"})
        self.assertTrue(res["success"])


if __name__ == "__main__":
    unittest.main()


class TestRepeatFetchAfterTheFileWasDeleted(unittest.TestCase):
    """The layer-adding step deletes a boundary's temp file, yet the network phase cached the path and reused it: a second fetch of the same country in one
    session got a path to nothing (a likely cause of the owner's W2/W3 rows). A cached result is reused only while its file exists."""

    def test_cache_is_used_while_the_file_exists_and_dropped_when_it_is_gone(self):
        import os
        import tempfile
        fd, path = tempfile.mkstemp()
        os.close(fd)
        entry = {"success": True, "local_path": path}
        try:
            self.assertIs(ht._cached_download(entry), entry)
        finally:
            os.remove(path)
        self.assertIsNone(ht._cached_download(entry))
        self.assertIsNone(ht._cached_download(None))
        no_file = {"success": True}
        self.assertIs(ht._cached_download(no_file), no_file)

    def test_a_cached_boundary_whose_file_was_deleted_is_downloaded_again(self):
        ht._LOOKUP_CACHE.set(("geoboundaries", "ZZZ", "ADM1"), {"success": True, "local_path": "/nonexistent/gone.geojson", "iso3": "ZZZ", "admin_level": "ADM1"})
        api = b'{"boundaryName": "x"}'                      # no file link, so a fresh download attempt is visible as an error
        with patch.object(ht.urllib.request, "urlopen", return_value=_Resp(api)) as asked:
            out = ht.fetch_geoboundaries_network_phase("ZZZ", "ADM1")
        asked.assert_called()
        self.assertIn("error", out)
