"""DEF-11 (hand run D6): the change-detection tool must accept what the prompt gives it, a file, not only a loaded layer's name."""
import os
import tempfile
import unittest

from cartogen_ai.core.agent.tools.raster_tools import resolve_raster_reference


class _Layer:
    def __init__(self, name, source):
        self._name, self._source = name, source

    def name(self):
        return self._name

    def source(self):
        return self._source


class TestResolve(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = os.path.join(self.tmp.name, "before_fixture.asc")
        open(self.file, "w").close()
        self.loaded_calls = []

    def _resolve(self, value, layers=()):
        by_name = {layer.name(): layer for layer in layers}

        def load_file(path):
            self.loaded_calls.append(path)
            return _Layer(os.path.splitext(os.path.basename(path))[0], path)

        return resolve_raster_reference(value, by_name.get, lambda: list(layers), load_file)

    def test_a_layer_name_wins_and_loads_nothing(self):
        layer = _Layer("before_fixture", self.file)
        self.assertEqual(self._resolve("before_fixture", [layer]), (layer, None))
        self.assertEqual(self.loaded_calls, [])

    def test_the_file_of_a_loaded_layer_finds_that_layer_without_loading_again(self):
        layer = _Layer("renamed", self.file + "|layername=x")
        self.assertEqual(self._resolve(self.file, [layer]), (layer, None))
        self.assertEqual(self.loaded_calls, [])

    def test_an_existing_file_not_in_the_project_is_loaded_and_the_note_says_so(self):
        layer, note = self._resolve(f'  "{self.file}"  ')
        self.assertEqual(layer.name(), "before_fixture")
        self.assertEqual(self.loaded_calls, [self.file])
        self.assertIn("was not in the project", note)
        self.assertIn("before_fixture", note)

    def test_a_file_name_with_extension_finds_the_layer_named_without_it(self):
        layer = _Layer("after_fixture", "/elsewhere/after_fixture.asc")
        self.assertEqual(self._resolve("after_fixture.asc", [layer]), (layer, None))
        self.assertEqual(self.loaded_calls, [])

    def test_a_missing_file_and_empty_values_resolve_to_nothing(self):
        self.assertEqual(self._resolve(os.path.join(self.tmp.name, "nope.asc")), (None, None))
        self.assertEqual(self._resolve(""), (None, None))
        self.assertEqual(self._resolve(None), (None, None))
        self.assertEqual(self.loaded_calls, [])

    def test_a_bare_name_that_is_not_a_layer_is_never_treated_as_a_file(self):
        self.assertEqual(self._resolve("before"), (None, None))
        self.assertEqual(self.loaded_calls, [])


if __name__ == "__main__":
    unittest.main()
