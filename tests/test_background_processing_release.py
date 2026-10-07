# -*- coding: utf-8 -*-
"""Audit A16: abandoned processing bundles are released once their task finishes (pure logic, no QGIS)."""
import unittest

from cartogen_ai.core.agent.tools import _background_processing as bp


class TestReleaseAbandoned(unittest.TestCase):
    def setUp(self):
        self._saved = list(bp._ABANDONED)
        bp._ABANDONED[:] = []
        self.addCleanup(lambda: bp._ABANDONED.__setitem__(slice(None), self._saved))

    def test_only_finished_entries_are_released(self):
        running, done = object(), object()
        bp._ABANDONED.extend([(running,), (done,)])
        released = bp.release_finished_abandoned(is_done=lambda task: task is done)
        self.assertEqual(released, 1)
        self.assertEqual(bp._ABANDONED, [(running,)])

    def test_unknown_status_keeps_the_entry(self):
        bp._ABANDONED.append((object(),))
        self.assertEqual(bp.release_finished_abandoned(), 0)     # no QGIS here -> cannot prove it finished
        self.assertEqual(len(bp._ABANDONED), 1)

    def test_abandon_tolerates_a_task_without_signals(self):
        entry = (object(), None, None, None, None)
        bp._abandon(entry)
        self.assertIn(entry, bp._ABANDONED)


if __name__ == "__main__":
    unittest.main()
