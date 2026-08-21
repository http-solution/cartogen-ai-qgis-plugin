# -*- coding: utf-8 -*-
import unittest
from ui.canvas_highlight import find_mentioned_layers


class _FakeLayer:
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name


class TestFindMentionedLayers(unittest.TestCase):
    def test_matches_layer_name_in_text(self):
        layers = [_FakeLayer("Jordan_Governorates"), _FakeLayer("Flood_Zones")]
        matched = find_mentioned_layers("I've buffered the Jordan_Governorates layer by 500m.", layers)
        self.assertEqual([l.name() for l in matched], ["Jordan_Governorates"])

    def test_case_insensitive_match(self):
        layers = [_FakeLayer("Roads")]
        matched = find_mentioned_layers("The roads layer now has a new field.", layers)
        self.assertEqual(len(matched), 1)

    def test_no_match_returns_empty(self):
        layers = [_FakeLayer("Jordan_Governorates")]
        matched = find_mentioned_layers("Here is a general summary with no layer names.", layers)
        self.assertEqual(matched, [])

    def test_short_names_ignored_to_avoid_false_positives(self):
        # A 2-character layer name shouldn't match generic prose.
        layers = [_FakeLayer("ID")]
        matched = find_mentioned_layers("This identifies each feature.", layers)
        self.assertEqual(matched, [])

    def test_respects_max_matches(self):
        layers = [_FakeLayer("Alpha_Layer"), _FakeLayer("Beta_Layer"), _FakeLayer("Gamma_Layer")]
        text = "Alpha_Layer, Beta_Layer, and Gamma_Layer were all processed."
        matched = find_mentioned_layers(text, layers, max_matches=2)
        self.assertEqual(len(matched), 2)

    def test_longer_names_preferred_over_substrings(self):
        layers = [_FakeLayer("Zone"), _FakeLayer("Flood_Zone")]
        matched = find_mentioned_layers("The Flood_Zone layer was updated.", layers, max_matches=1)
        self.assertEqual(matched[0].name(), "Flood_Zone")


if __name__ == "__main__":
    unittest.main()
