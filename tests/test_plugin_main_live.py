# -*- coding: utf-8 -*-
"""Live QGIS test of plugin_main.CartogenAi's load/unload lifecycle.

P1 finding, 2026-09-20 audit: initGui() parents its QActions to
iface.mainWindow() and connects their `triggered` signal to bound methods on
the CartogenAi instance. unload() used to only call
removePluginMenu/removeToolBarIcon -- both just detach the action from a UI
container, neither disconnects the signal nor destroys the QAction. A real
load -> unload -> reload cycle (QGIS's own Plugin Reloader, or a user
disabling/re-enabling the plugin) would accumulate live, connected actions
and keep the old CartogenAi instance reachable through them.

Requires real qgis.core + qgis.PyQt bindings, like test_chat_widget_live.py.
Run from an OSGeo4W/QGIS Python: `python -m unittest tests.test_plugin_main_live -v`.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from qgis.core import QgsApplication
    from qgis.PyQt import sip
    from qgis.PyQt.QtCore import QEventLoop, QTimer
    from qgis.PyQt.QtWidgets import QMainWindow
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False

_APP = None


def _boot_qgis():
    global _APP
    if _APP is None:
        _APP = QgsApplication([b"plugintest"], False)
        QgsApplication.setPrefixPath("/usr", True)
        _APP.initQgis()
    return _APP


def _pump(ms=200):
    """Runs the real Qt event loop briefly so a deleteLater() scheduled during
    unload() actually gets processed -- deleteLater() only marks an object for
    deletion on the next pass of the event loop, it doesn't delete synchronously."""
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


class _FakeMessageBar:
    def pushWarning(self, *args, **kwargs):
        pass

    def pushMessage(self, *args, **kwargs):
        pass


class _FakeIface:
    """Minimal stand-in for QgisInterface covering only what plugin_main.py
    calls -- real QMainWindow underneath so QAction parenting/signal behavior
    is the genuine Qt behavior, not a mock."""

    def __init__(self, main_window):
        self._main_window = main_window
        self.menu_actions = []
        self.toolbar_actions = []

    def mainWindow(self):
        return self._main_window

    def addToolBarIcon(self, action):
        self.toolbar_actions.append(action)

    def removeToolBarIcon(self, action):
        if action in self.toolbar_actions:
            self.toolbar_actions.remove(action)

    def addPluginToMenu(self, name, action):
        self.menu_actions.append(action)

    def removePluginMenu(self, name, action):
        if action in self.menu_actions:
            self.menu_actions.remove(action)

    def addDockWidget(self, area, widget):
        self._main_window.addDockWidget(area, widget)

    def removeDockWidget(self, widget):
        self._main_window.removeDockWidget(widget)

    def messageBar(self):
        return _FakeMessageBar()


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core/qgis.PyQt bindings -- run from an OSGeo4W/QGIS Python")
class TestPluginMainLifecycleLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _boot_qgis()

    def setUp(self):
        self.main_window = QMainWindow()
        self.iface = _FakeIface(self.main_window)
        self.addCleanup(self.main_window.deleteLater)

    def _make_plugin(self):
        import plugin_main
        plugin = plugin_main.CartogenAi(self.iface)
        plugin.initGui()
        return plugin

    def test_the_panel_opens_at_startup_unless_the_setting_is_off(self):
        from qgis.core import QgsSettings
        from cartogen_ai.infrastructure.settings_keys import SETTINGS_AUTO_OPEN_DOCK as KEY
        settings = QgsSettings()
        self.addCleanup(settings.remove, KEY)
        settings.setValue(KEY, False)
        plugin = self._make_plugin()
        self.addCleanup(plugin.unload)
        plugin._auto_open_dock()
        self.assertIsNone(plugin.dock_widget, "setting off -> the dock is not created at startup")
        settings.setValue(KEY, True)
        plugin._auto_open_dock()
        self.assertIsNotNone(plugin.dock_widget, "default/on -> the dock is created and shown")
        self.assertTrue(plugin.toolbar_action.isChecked())
        dock = plugin.dock_widget
        plugin._auto_open_dock()
        self.assertIs(plugin.dock_widget, dock, "a second call must not create another dock")

    def test_unload_disconnects_action_signals(self):
        plugin = self._make_plugin()
        actions = list(plugin.actions)
        self.assertEqual(len(actions), 2, "expected the toolbar action + Help action")

        for action in actions:
            # A freshly-connected signal has exactly one receiver (initGui's own
            # connect); disconnect() with no args succeeds when there's >=1
            # receiver and raises TypeError when there are none.
            action.triggered.disconnect()
            action.triggered.connect(lambda *_: None)  # restore so unload() has something real to undo

        plugin.unload()

        for action in actions:
            with self.assertRaises((TypeError, RuntimeError)):
                action.triggered.disconnect()

    def test_unload_schedules_actions_for_deletion(self):
        plugin = self._make_plugin()
        actions = list(plugin.actions)

        plugin.unload()
        _pump()

        for action in actions:
            self.assertTrue(sip.isdeleted(action),
                             "action must be deleted (not just detached from the menu/toolbar) after unload()")

    def test_unload_clears_action_bookkeeping(self):
        plugin = self._make_plugin()
        plugin.unload()
        self.assertEqual(plugin.actions, [])
        self.assertIsNone(plugin.toolbar_action)

    def test_reload_after_unload_does_not_accumulate_live_actions(self):
        """The actual regression scenario: QGIS's Plugin Reloader (or a manual
        disable/enable) calls unload() then initGui() again on a fresh instance.
        Before the fix, the first instance's actions stayed alive and connected
        alongside the second instance's -- this proves only the second
        instance's actions remain live."""
        first = self._make_plugin()
        first_actions = list(first.actions)
        first.unload()
        _pump()

        second = self._make_plugin()
        second_actions = list(second.actions)

        for action in first_actions:
            self.assertTrue(sip.isdeleted(action))
        for action in second_actions:
            self.assertFalse(sip.isdeleted(action))

        second.unload()
        _pump()


if __name__ == "__main__":
    unittest.main()
