# -*- coding: utf-8 -*-
"""The closure rule (audit F19, #155), offline. The network copy needs QGIS: tests/test_network_closure_live.py."""
import unittest

from cartogen_ai.core.agent.tools import logistics_tools as lt
from cartogen_ai.core.agent.tools._network_closure import CLOSED_SPEED_KMH, is_closed, routable_network


class TestIsClosed(unittest.TestCase):
    def test_only_negative_numbers_are_closed(self):
        self.assertTrue(is_closed(CLOSED_SPEED_KMH))
        self.assertTrue(is_closed("-3"))
        # 0 and NULL are "unset" in real OSM data (maxspeed is 0/empty on >99% of roads): never a closure.
        for value in (0, 0.0, None, "", "fast", 30, "30"):
            self.assertFalse(is_closed(value), value)


class TestRoutableNetworkWithoutAField(unittest.TestCase):
    def test_no_speed_field_returns_the_layer_untouched(self):
        sentinel = object()
        self.assertEqual(routable_network(sentinel, None), (sentinel, 0, None))


class TestClosedNote(unittest.TestCase):
    def test_nothing_closed_adds_nothing(self):
        self.assertEqual(lt._closed_note(0), {})

    def test_closures_are_reported(self):
        note = lt._closed_note(4)
        self.assertEqual(note["closed_segments_removed"], 4)
        self.assertIn("removed from the network", note["closed_note"])


if __name__ == "__main__":
    unittest.main()
