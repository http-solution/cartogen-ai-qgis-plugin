"""PLAN-021 WP-C (#223), real QGIS (CI live job; written without a QGIS install, so CI's first run is its first execution): an abandoned
processing bundle is released by its task's own finish signal, and a Stopped analysis leaves nothing behind."""
import time
import unittest

from tests.test_network_units_live import QGIS_LIVE_AVAILABLE, _boot

if QGIS_LIVE_AVAILABLE:
    from qgis.core import QgsApplication, QgsTask
    from qgis.PyQt.QtCore import QCoreApplication


def _pump(until, seconds=15.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if until():
            return True
        time.sleep(0.02)
    return until()


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core bindings")
class TestAbandonedBundlesAreReleased(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        why = _boot()
        if why:
            raise unittest.SkipTest(why)
        from cartogen_ai.core.agent.tools import _background_processing as bg
        cls.bg = bg

    def setUp(self):
        saved = list(self.bg._ABANDONED)
        self.bg._ABANDONED[:] = []
        self.addCleanup(lambda: self.bg._ABANDONED.__setitem__(slice(None), saved))

    def test_a_task_that_finishes_after_being_abandoned_releases_its_entry_by_itself(self):
        task = QgsTask.fromFunction("cartogen abandoned test", lambda t: True)
        self.bg._abandon((task, None, None, None, None))
        self.assertEqual(len(self.bg._ABANDONED), 1)
        QgsApplication.taskManager().addTask(task)
        self.assertTrue(_pump(lambda: not self.bg._ABANDONED), f"still held: {len(self.bg._ABANDONED)} entries after the task finished")

    def test_a_task_that_is_cancelled_releases_its_entry_too(self):
        def spin(task):
            while not task.isCanceled():
                time.sleep(0.01)
            return False
        task = QgsTask.fromFunction("cartogen cancelled test", spin)
        self.bg._abandon((task, None, None, None, None))
        QgsApplication.taskManager().addTask(task)
        _pump(lambda: False, 0.3)
        task.cancel()
        self.assertTrue(_pump(lambda: not self.bg._ABANDONED), "a cancelled task's bundle was never released")

    def test_a_running_task_keeps_its_entry_until_it_stops(self):
        def spin(task):
            while not task.isCanceled():
                time.sleep(0.01)
            return False
        task = QgsTask.fromFunction("cartogen running test", spin)
        self.bg._abandon((task, None, None, None, None))
        QgsApplication.taskManager().addTask(task)
        _pump(lambda: False, 0.4)
        self.assertEqual(self.bg.release_finished_abandoned(), 0, "released while the worker thread was still running")
        task.cancel()
        self.assertTrue(_pump(lambda: not self.bg._ABANDONED))


if __name__ == "__main__":
    unittest.main()
