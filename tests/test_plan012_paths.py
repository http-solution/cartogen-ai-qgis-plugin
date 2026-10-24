"""PLAN-012 items 2 and 3, no QGIS needed: a safe, unique GeoJSON file name, and the note that says where temporary files are."""
import os
import tempfile
import unittest

from cartogen_ai.core.agent.tools._paths import safe_file_stem, temp_location_note, unique_path


class TestSafeFileStem(unittest.TestCase):
    def test_path_traversal_and_separators_become_a_plain_name(self):
        for hostile in ("../../etc/passwd", "..\\..\\evil", "/abs/path", "a/b", "C:\\x\\y"):
            stem = safe_file_stem(hostile)
            self.assertNotIn("/", stem)
            self.assertNotIn("\\", stem)
            self.assertFalse(stem.startswith("."), stem)
            self.assertNotEqual(stem, "")

    def test_dots_only_or_empty_use_the_fallback(self):
        self.assertEqual(safe_file_stem("..", "mapping_tasks"), "mapping_tasks")
        self.assertEqual(safe_file_stem("", "mapping_tasks"), "mapping_tasks")
        self.assertEqual(safe_file_stem(None, "mapping_tasks"), "mapping_tasks")

    def test_an_ordinary_name_is_kept(self):
        self.assertEqual(safe_file_stem("mapping_tasks"), "mapping_tasks")
        self.assertEqual(safe_file_stem("Tasks 2024-05"), "Tasks 2024-05")

    def test_the_result_always_stays_inside_the_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            for hostile in ("../x", "../../x", "/etc/x", "a/../../x"):
                path = unique_path(tmp, safe_file_stem(hostile), ".geojson")
                self.assertEqual(os.path.dirname(os.path.realpath(path)), os.path.realpath(tmp), hostile)


class TestUniquePath(unittest.TestCase):
    def test_a_free_name_is_used_as_it_is(self):
        self.assertEqual(unique_path("/t", "grid", ".geojson", exists=lambda p: False), os.path.join("/t", "grid.geojson"))

    def test_an_existing_file_is_never_overwritten(self):
        taken = {os.path.join("/t", "grid.geojson"), os.path.join("/t", "grid_2.geojson")}
        self.assertEqual(unique_path("/t", "grid", ".geojson", exists=taken.__contains__), os.path.join("/t", "grid_3.geojson"))

    def test_against_real_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = unique_path(tmp, "grid", ".geojson")
            with open(first, "w") as handle:
                handle.write("{}")
            self.assertNotEqual(unique_path(tmp, "grid", ".geojson"), first)


class TestTempLocationNote(unittest.TestCase):
    def test_a_file_in_the_temp_folder_gets_the_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            note = temp_location_note(os.path.join(tmp, "dem.tif"), temp_dir=tmp)
        self.assertIn("system temporary folder", note)

    def test_a_file_elsewhere_gets_none(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as elsewhere:
            self.assertEqual(temp_location_note(os.path.join(elsewhere, "dem.tif"), temp_dir=tmp), "")

    def test_a_sibling_folder_with_the_same_prefix_is_not_inside(self):
        with tempfile.TemporaryDirectory() as parent:
            temp = os.path.join(parent, "tmp")
            sibling = os.path.join(parent, "tmp_other")
            os.makedirs(temp)
            os.makedirs(sibling)
            self.assertEqual(temp_location_note(os.path.join(sibling, "x.tif"), temp_dir=temp), "")

    def test_empty_path_gets_none(self):
        self.assertEqual(temp_location_note(""), "")


if __name__ == "__main__":
    unittest.main()
