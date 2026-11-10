"""PLAN-072 / HU-5 part 3: mark superseded. Offline, with stand-in layers; the real-QGIS half is tests/test_superseded_layers_live.py."""
import unittest
from unittest import mock

from cartogen_ai.core.agent import superseded as sup


class Layer:
    def __init__(self, lid, name, tool=None, stamp="2026-11-09 10:00:00"):
        self._id, self._name, self.props = lid, name, {}
        self.lineage = [{"tool": tool, "timestamp": stamp}] if tool else []

    def id(self):
        return self._id

    def name(self):
        return self._name

    def setName(self, name):
        self._name = name

    def customProperty(self, key, default=None):
        return self.props.get(key, default)

    def setCustomProperty(self, key, value):
        self.props[key] = value


class Project:
    def __init__(self, layers):
        self.layers = layers

    def mapLayers(self):
        return {lyr.id(): lyr for lyr in self.layers}

    def mapLayersByName(self, name):
        return [lyr for lyr in self.layers if lyr.name() == name]


def run(project, new_layer, tool, before):
    with mock.patch.object(sup, "get_layer_lineage", lambda layer: layer.lineage):
        return sup.mark_older(project, new_layer, tool, before)


class TestPureRules(unittest.TestCase):
    def test_the_name_is_numbered_when_taken(self):
        self.assertEqual(sup.superseded_name("Buffered", set()), "Buffered (superseded)")
        self.assertEqual(sup.superseded_name("Buffered", {"Buffered (superseded)"}), "Buffered (superseded 2)")
        self.assertEqual(sup.superseded_name("Buffered", {"Buffered (superseded)", "Buffered (superseded 2)"}), "Buffered (superseded 3)")

    def test_loading_tools_never_supersede(self):
        for tool in ("add_layer_from_path", "add_postgis_layer", "load_layer_definition", "import_humanitarian_table", "create_empty_layer", "", None):
            self.assertFalse(sup.tool_may_supersede(tool), tool)
        for tool in ("buffer_layer", "calculate_service_area", "fetch_osm_data", "run_allowlisted_processing"):
            self.assertTrue(sup.tool_may_supersede(tool), tool)

    def test_the_new_layer_is_the_one_not_loaded_before_the_call(self):
        old, new = Layer("a", "X"), Layer("b", "X")
        self.assertIs(sup.pick_new_layer([old, new], {"a"}), new)
        self.assertIs(sup.pick_new_layer([new, old], {"a"}), new)
        self.assertIs(sup.pick_new_layer([old, new], None), old)             # two-phase path: unchanged behaviour
        self.assertIs(sup.pick_new_layer([old], {"a"}), old)                 # the call changed an existing layer
        self.assertIsNone(sup.pick_new_layer([], {"a"}))

    def test_the_note_names_each_renamed_layer(self):
        text = sup.note([{"was": "X", "now": "X (superseded)"}])
        self.assertIn("'X' is now 'X (superseded)'", text)
        self.assertIn("Nothing was deleted", text)


class TestMarkOlder(unittest.TestCase):
    def test_a_rerun_of_the_same_tool_keeps_the_older_result_under_a_new_name(self):
        old, new = Layer("a", "Buffered", "buffer_layer"), Layer("b", "Buffered")
        renamed = run(Project([old, new]), new, "buffer_layer", {"a"})
        self.assertEqual(renamed, [{"was": "Buffered", "now": "Buffered (superseded)"}])
        self.assertEqual((old.name(), new.name()), ("Buffered (superseded)", "Buffered"))
        self.assertEqual(old.props[sup.SUPERSEDED_KEY], "b")

    def test_nothing_is_deleted_or_moved(self):
        layers = [Layer("a", "Buffered", "buffer_layer"), Layer("b", "Buffered")]
        project = Project(layers)
        run(project, layers[1], "buffer_layer", {"a"})
        self.assertEqual(sorted(project.mapLayers()), ["a", "b"])

    def test_a_layer_the_user_made_is_never_renamed(self):
        user, new = Layer("a", "Buffered"), Layer("b", "Buffered")      # no lineage: not made by this plugin
        self.assertEqual(run(Project([user, new]), new, "buffer_layer", {"a"}), [])
        self.assertEqual(user.name(), "Buffered")

    def test_another_tools_output_with_the_same_name_is_not_renamed(self):
        other, new = Layer("a", "Result", "clip_layer"), Layer("b", "Result")
        self.assertEqual(run(Project([other, new]), new, "buffer_layer", {"a"}), [])
        self.assertEqual(other.name(), "Result")

    def test_a_loading_tool_never_supersedes_even_when_the_lineage_matches(self):
        old, new = Layer("a", "roads", "add_layer_from_path"), Layer("b", "roads")
        self.assertEqual(run(Project([old, new]), new, "add_layer_from_path", {"a"}), [])
        self.assertEqual(old.name(), "roads")

    def test_without_the_layers_present_before_the_call_nothing_happens(self):
        old, new = Layer("a", "Buffered", "buffer_layer"), Layer("b", "Buffered")
        self.assertEqual(run(Project([old, new]), new, "buffer_layer", None), [])

    def test_a_layer_made_by_the_same_call_is_not_superseded(self):
        first, second = Layer("a", "Reach", "calculate_service_area"), Layer("b", "Reach")
        self.assertEqual(run(Project([first, second]), second, "calculate_service_area", set()), [])

    def test_several_earlier_results_are_numbered_oldest_first(self):
        o1 = Layer("a", "Buffered", "buffer_layer", "2026-11-09 09:00:00")
        o2 = Layer("b", "Buffered", "buffer_layer", "2026-11-09 10:00:00")
        new = Layer("c", "Buffered")
        run(Project([o2, o1, new]), new, "buffer_layer", {"a", "b"})
        self.assertEqual((o1.name(), o2.name()), ("Buffered (superseded)", "Buffered (superseded 2)"))

    def test_a_failure_never_raises(self):
        broken = mock.Mock()
        broken.mapLayersByName.side_effect = RuntimeError("wrapped C/C++ object deleted")
        self.assertEqual(sup.mark_older(broken, Layer("b", "X"), "buffer_layer", {"a"}), [])


class TestSetting(unittest.TestCase):
    def test_on_by_default_outside_qgis(self):
        with mock.patch.object(sup, "QGIS_AVAILABLE", False):
            self.assertTrue(sup.enabled())


if __name__ == "__main__":
    unittest.main()
