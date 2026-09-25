# -*- coding: utf-8 -*-
"""Network analysis no longer freezes QGIS: it runs on a worker thread and can be stopped (real QGIS).

Live-reported 2026-09-25 (BUG-2026-09-25-2): routing over a national road network (161,041 roads)
took 292-572 s per call on QGIS's GUI thread; the window showed "Not Responding" and nothing could
stop it. Prototyped on the real 39,017-road network first: 293 UI ticks during an 18.5 s run (worst
gap 77 ms), identical results, cancel returned 0.0 s after it was requested. These tests pin that on a
synthetic grid sized to take a few seconds, so they run in CI as well.

Needs real qgis.core + the Processing plugin (skipped otherwise)."""
import threading
import time
import unittest
from unittest.mock import patch

from tests.test_network_units_live import QGIS_LIVE_AVAILABLE, _boot

if QGIS_LIVE_AVAILABLE:
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsSettings, QgsVectorLayer
    from qgis.PyQt.QtCore import QTimer

WEST, SOUTH, SPAN = 35.8, 31.9, 0.2


def _grid(n, verts, name="roads"):
    """n horizontal + n vertical lines, `verts` segments each, over a 0.2 degree square (~20 km)."""
    lyr = QgsVectorLayer("LineString?crs=EPSG:4326&field=id:int", name, "memory")
    step = SPAN / n
    feats = []
    for i in range(n):
        for horizontal in (True, False):
            pts = [QgsPointXY(WEST + (k / verts) * SPAN, SOUTH + i * step) if horizontal else
                   QgsPointXY(WEST + i * step, SOUTH + (k / verts) * SPAN) for k in range(verts + 1)]
            f = QgsFeature(lyr.fields())
            f.setGeometry(QgsGeometry.fromPolylineXY(pts))
            feats.append(f)
    lyr.dataProvider().addFeatures(feats)
    QgsProject.instance().addMapLayer(lyr)
    return lyr


def _points(name, lonlats):
    lyr = QgsVectorLayer("Point?crs=EPSG:4326&field=id:int", name, "memory")
    feats = []
    for x, y in lonlats:
        f = QgsFeature(lyr.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
        feats.append(f)
    lyr.dataProvider().addFeatures(feats)
    QgsProject.instance().addMapLayer(lyr)
    return lyr


ORIGIN = (WEST + 0.1, SOUTH + 0.1)                  # on a grid line crossing
DEST = (WEST + 0.1 + 0.004, SOUTH + 0.1)            # ~380 m east


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core bindings -- run from an OSGeo4W/QGIS Python")
class TestBackgroundNetworkAnalysis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        why = _boot()
        if why:
            raise unittest.SkipTest(why)
        from cartogen_ai.core.agent import cancel_signal
        from cartogen_ai.core.agent.tools import _background_processing as bg
        from cartogen_ai.core.agent.tools import logistics_tools as lt
        cls.lt, cls.bg, cls.cancel_signal = lt, bg, cancel_signal

    def setUp(self):
        QgsProject.instance().clear()
        QgsProject.instance().setEllipsoid("NONE")
        self.addCleanup(QgsProject.instance().clear)
        self.addCleanup(self.cancel_signal.end)
        # These tests need an analysis that is SLOW, to prove the worker thread keeps the GUI alive and
        # that Stop interrupts it. Clipping the network to the service area's reach (tests/
        # test_network_clip_live.py) makes these small grids fast (72 of 1,200 roads, 0.14 s), so it is
        # switched off here; its own behaviour is tested there.
        clip = patch.object(self.lt, "_clip_network_to_reach", side_effect=lambda net, centre, reach: (net, {"applied": False}))
        clip.start()
        self.addCleanup(clip.stop)

    def scene(self, n, verts):
        _grid(n, verts)
        _points("origin", [ORIGIN])
        _points("dest", [DEST])

    _SLOW_N = None

    @classmethod
    def slow_grid_size(cls):
        """The smallest grid (n lines each way, 30 segments each) whose analysis takes at least 2 s ON THE
        MACHINE RUNNING THE TEST. A fixed size can't be right everywhere: 1,200 roads took 3.2 s on a
        laptop and 0.7 s on the CI runner, so the "long enough to prove anything" guards below passed in
        one CI run and failed in the next (PR #31). Calibrated once per run, about 3 s."""
        if cls._SLOW_N is None:
            import processing
            for n in (600, 1200, 2400, 4800):
                QgsProject.instance().clear()
                lyr = _grid(n, 30, name="calibration")
                started = time.monotonic()
                processing.run("native:serviceareafrompoint", {
                    "INPUT": lyr, "STRATEGY": 0, "TOLERANCE": 0, "DEFAULT_SPEED": 50,
                    "START_POINT": "%s,%s" % ORIGIN, "TRAVEL_COST2": 500, "OUTPUT_LINES": "memory:"},
                    context=cls.lt._network_context())
                cls._SLOW_N = n
                if time.monotonic() - started >= 2.0:
                    break
            QgsProject.instance().clear()
        return cls._SLOW_N

    def hulls_and_lines(self):
        return [lyr for lyr in QgsProject.instance().mapLayers().values() if "service_area" in lyr.name()]

    # ------------------------------------------------------------------------------ results --

    def test_background_result_is_identical_to_the_synchronous_one(self):
        self.scene(120, 30)
        outcomes = {}
        for mode, threshold in (("background", 1), ("synchronous", 10 ** 9)):
            QgsProject.instance().removeMapLayers([lyr.id() for lyr in self.hulls_and_lines()])
            with patch.object(self.lt, "BACKGROUND_MIN_FEATURES", threshold), \
                 patch.object(self.bg, "QgsProcessingAlgRunnerTask", wraps=self.bg.QgsProcessingAlgRunnerTask) as task_cls:
                sa = self.lt.calculate_service_area("origin", "roads", 500)
                tm = self.lt.travel_time_matrix("origin", "dest", "roads")
            self.assertTrue(sa.get("success") and tm.get("success"), (sa, tm))
            lines = QgsProject.instance().mapLayersByName(sa["layers_created"][0])[0]
            outcomes[mode] = (lines.featureCount(), round(sum(f.geometry().length() for f in lines.getFeatures()), 6),
                              round(float(list(list(tm["matrix"].values())[0].values())[0]), 3))
            # the background path really used a worker task; the synchronous one did not
            self.assertEqual(task_cls.call_count, 2 if mode == "background" else 0, mode)
        self.assertEqual(outcomes["background"], outcomes["synchronous"])
        self.assertGreater(outcomes["background"][0], 0)

    # -------------------------------------------------------------------------- responsiveness --

    def test_the_gui_keeps_running_while_the_analysis_works(self):
        self.scene(self.slow_grid_size(), 30)
        ticks = []
        timer = QTimer()
        timer.setInterval(50)
        timer.timeout.connect(lambda: ticks.append(time.monotonic()))
        timer.start()
        self.addCleanup(timer.stop)
        started = time.monotonic()
        with patch.object(self.lt, "BACKGROUND_MIN_FEATURES", 1):
            sa = self.lt.calculate_service_area("origin", "roads", 500)
        duration = time.monotonic() - started
        timer.stop()
        self.assertTrue(sa.get("success"), sa)
        # guard: the analysis has to be long enough for "kept ticking" to mean something
        self.assertGreater(duration, 1.0, "test network too small to show anything")
        gaps = [b - a for a, b in zip(ticks, ticks[1:])]
        # measured on the real 39,017-road network: 293 ticks in 18.5 s, worst gap 77 ms (timer 50 ms).
        # A synchronous run gives ~0 ticks (that is the freeze). Generous bounds for slow CI machines.
        self.assertGreater(len(ticks), 0.4 * duration / 0.05, "ticks=%d duration=%.1fs" % (len(ticks), duration))
        self.assertLess(max(gaps), 0.5, "worst UI gap %.0f ms" % (max(gaps) * 1000))

    def test_the_synchronous_path_is_what_freezes(self):
        """The control: the same analysis run synchronously gives the UI (almost) no ticks, so the test
        above is measuring the fix and not a lenient timer."""
        self.scene(self.slow_grid_size(), 30)
        ticks = []
        timer = QTimer()
        timer.setInterval(50)
        timer.timeout.connect(lambda: ticks.append(time.monotonic()))
        timer.start()
        self.addCleanup(timer.stop)
        started = time.monotonic()
        with patch.object(self.lt, "BACKGROUND_MIN_FEATURES", 10 ** 9):
            self.lt.calculate_service_area("origin", "roads", 500)
        duration = time.monotonic() - started
        timer.stop()
        self.assertGreater(duration, 1.0)
        self.assertLess(len(ticks), 0.2 * duration / 0.05, "ticks=%d duration=%.1fs" % (len(ticks), duration))

    # -------------------------------------------------------------------------------------- Stop --

    def test_stop_ends_the_analysis_promptly_and_leaves_the_project_alone(self):
        self.scene(self.slow_grid_size(), 30)
        t0 = time.monotonic()
        self.cancel_signal.begin(should_stop=lambda: time.monotonic() - t0 > 0.5)
        layers_before = set(QgsProject.instance().mapLayers())
        with patch.object(self.lt, "BACKGROUND_MIN_FEATURES", 1):
            sa = self.lt.calculate_service_area("origin", "roads", 500)
            tm = self.lt.travel_time_matrix("origin", "dest", "roads")
        elapsed = time.monotonic() - t0
        self.assertTrue(sa.get("cancelled"), sa)
        self.assertTrue(tm.get("cancelled"), tm)
        self.assertIn("Stopped", sa["error"])
        self.assertLess(elapsed, 5.0, "took %.1fs to stop" % elapsed)   # unstopped: ~3 s + ~3 s each
        self.assertEqual(set(QgsProject.instance().mapLayers()), layers_before)   # nothing was added
        # ...and QGIS is fine afterwards: the next request works normally
        self.cancel_signal.end()
        _grid(40, 6, name="roads_small")
        again = self.lt.calculate_service_area("origin", "roads_small", 200)
        self.assertTrue(again.get("success"), again)

    def test_an_old_stop_does_not_cancel_a_later_analysis(self):
        # agent.run() clears its registration; a stale should_stop must never abort a tool run later
        self.scene(60, 10)
        token = self.cancel_signal.begin(should_stop=lambda: True)
        self.cancel_signal.end(token)
        with patch.object(self.lt, "BACKGROUND_MIN_FEATURES", 1):
            sa = self.lt.calculate_service_area("origin", "roads", 200)
        self.assertTrue(sa.get("success"), sa)

    # -------------------------------------------------------------------------- the runner itself --

    def _params(self, network, **over):
        p = {"INPUT": network, "STRATEGY": 0, "TOLERANCE": 0, "DEFAULT_SPEED": 50,
             "START_POINT": "%s,%s" % ORIGIN, "TRAVEL_COST2": 500, "OUTPUT_LINES": "memory:"}
        p.update(over)
        return p

    def _run(self, params, **kw):
        import processing
        ctx = self.lt._network_context()
        return self.bg.run_algorithm("native:serviceareafrompoint", params, ctx,
                                     fallback=lambda a, p, context=None: processing.run(a, p, context=context), **kw)

    def test_progress_is_reported_while_it_works(self):
        network = _grid(self.slow_grid_size(), 30)
        messages = []
        self.cancel_signal.begin(status=messages.append)
        self._run(self._params(network), label="Service area", status_every_s=0.2, first_status_after_s=0.2)
        self.assertTrue(any("Service area" in m and "press Stop" in m for m in messages), messages)

    def test_a_failing_algorithm_raises_with_its_own_message(self):
        network = _grid(20, 4)
        with self.assertRaises(RuntimeError) as ctx:
            self._run(self._params(network, INPUT="no such layer"))
        self.assertNotIsInstance(ctx.exception, self.bg.AnalysisCancelled)
        self.assertTrue(str(ctx.exception).strip())

    def test_the_kill_switch_restores_the_synchronous_behaviour(self):
        from cartogen_ai.infrastructure.settings_keys import SETTINGS_BACKGROUND_NETWORK_ANALYSIS
        settings = QgsSettings()
        self.addCleanup(settings.remove, SETTINGS_BACKGROUND_NETWORK_ANALYSIS)
        self.assertTrue(self.bg.can_run_in_background())
        settings.setValue(SETTINGS_BACKGROUND_NETWORK_ANALYSIS, False)
        self.assertFalse(self.bg.can_run_in_background())
        network = _grid(20, 4)
        with patch.object(self.bg, "QgsProcessingAlgRunnerTask", wraps=self.bg.QgsProcessingAlgRunnerTask) as task_cls:
            out = self._run(self._params(network))
        self.assertEqual(task_cls.call_count, 0)
        self.assertIn("OUTPUT_LINES", out)

    def test_it_only_runs_in_the_background_on_the_gui_thread(self):
        seen = []
        t = threading.Thread(target=lambda: seen.append(self.bg.can_run_in_background()))
        t.start()
        t.join()
        self.assertEqual(seen, [False])


if __name__ == "__main__":
    unittest.main()
