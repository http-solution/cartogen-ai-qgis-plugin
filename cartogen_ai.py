# -*- coding: utf-8 -*-
import os.path
import traceback

from qgis.PyQt.QtCore import Qt, QCoreApplication, QLocale, QTranslator
from qgis.PyQt.QtGui import QIcon

try:
    from qgis.PyQt.QtGui import QAction
except ImportError:
    from qgis.PyQt.QtWidgets import QAction

from qgis.core import QgsSettings, QgsProject

SETTINGS_KEY = "cartogen_ai/api_key"


def _dock_area_right():
    area = getattr(Qt, "RightDockWidgetArea", None)
    if area is not None:
        return area
    return Qt.DockWidgetArea.RightDockWidgetArea


class CartogenAi:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)

        try:
            locale = QgsSettings().value("locale/userLocale", QLocale().name())[0:2]
            locale_path = os.path.join(self.plugin_dir, "i18n", f"{locale}.qm")
            if os.path.exists(locale_path):
                self.translator = QTranslator()
                self.translator.load(locale_path)
                QCoreApplication.installTranslator(self.translator)
        except Exception as e:
            print(f"[CartogenAi] locale init failed: {e}")

        self.actions = []
        self.menu = self.tr("&Cartogen AI")
        self.dock_widget = None
        self.toolbar_action = None
        self._agent = None
        self._agent_key = None

    def tr(self, message):
        return QCoreApplication.translate("CartogenAi", message)

    def initGui(self):
        print("[CartogenAi] initGui()")
        icon_path = os.path.join(self.plugin_dir, "icon.png")
        action = QAction(QIcon(icon_path), self.tr("Cartogen AI"), self.iface.mainWindow())
        action.setCheckable(True)
        action.triggered.connect(self.toggle_dock)
        self.iface.addToolBarIcon(action)
        self.iface.addPluginToMenu(self.menu, action)
        self.actions.append(action)
        self.toolbar_action = action
        print("[CartogenAi] toolbar action installed")

        # The agent instance and dock widget are cached/reused across QGIS
        # project switches (see _get_agent()), so without this the chat panel
        # would keep showing the previous project's conversation after the
        # user opens a different .qgz. QgsProject.instance() is a singleton,
        # so it's safe to connect once here.
        project = QgsProject.instance()
        project.readProject.connect(self._on_project_changed)
        project.cleared.connect(self._on_project_changed)

    def _on_project_changed(self, *_args):
        if self._agent is not None:
            try:
                self._agent.reload_chat_history()
            except Exception as e:
                print(f"[CartogenAi] chat history reload failed: {e}")
        if self.dock_widget is not None:
            try:
                self.dock_widget.refresh_chat_for_project_change()
            except Exception as e:
                print(f"[CartogenAi] chat display refresh failed: {e}")

    def unload(self):
        print("[CartogenAi] unload()")
        try:
            project = QgsProject.instance()
            project.readProject.disconnect(self._on_project_changed)
            project.cleared.disconnect(self._on_project_changed)
        except (TypeError, RuntimeError):
            pass

        try:
            from .agent.scheduler import get_scheduler
            get_scheduler().stop_all()
        except Exception as e:
            print(f"[CartogenAi] scheduler stop_all failed: {e}")

        if self.dock_widget is not None:
            try:
                self.iface.removeDockWidget(self.dock_widget)
                self.dock_widget.deleteLater()
            except Exception as e:
                print(f"[CartogenAi] removeDockWidget failed: {e}")
            self.dock_widget = None

        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        self.actions = []

    def _get_agent(self):
        from .agent.auth import CredentialManager
        settings = QgsSettings()
        provider = settings.value("cartogen_ai/provider", "openrouter")
        key = CredentialManager.get_credential(provider)
        agent_hash = f"{provider}_{key}"

        if self._agent is None or getattr(self, "_agent_key", None) != agent_hash:
            try:
                from .agent.agent import CartogenAi as AgentCore
                self._agent = AgentCore()
                self._agent_key = agent_hash
            except Exception as e:
                print(f"[CartogenAi] agent init failed: {e}")
                traceback.print_exc()
                self._agent = None
                self._agent_key = None
                return None
        return self._agent

    def _ensure_dock(self):
        """Returns (ok, just_created). just_created matters to toggle_dock:
        iface.addDockWidget() makes a newly added dock visible immediately, so
        the caller must not then run its normal visible->hide toggle check
        against a dock that only just appeared -- that was the actual cause of
        needing two clicks after a fresh install (click 1 created-and-then-
        immediately-hid the panel; click 2 was what actually showed it)."""
        if self.dock_widget is not None:
            return True, False
        try:
            from .ui.dock_widget import CartogenAiDockWidget
            print("[CartogenAi] creating dock widget...")
            self.dock_widget = CartogenAiDockWidget(
                agent_provider=self._get_agent,
                parent=self.iface.mainWindow(),
            )
            # Connected before addDockWidget so it also catches the initial
            # visibility change addDockWidget itself triggers, not just later
            # user-driven show()/hide() calls.
            self.dock_widget.visibilityChanged.connect(self._on_dock_visibility)
            self.iface.addDockWidget(_dock_area_right(), self.dock_widget)
            print("[CartogenAi] dock widget added to right area")
            return True, True
        except Exception as e:
            print(f"[CartogenAi] _ensure_dock failed: {e}")
            traceback.print_exc()
            self.iface.messageBar().pushWarning(
                "Cartogen AI",
                f"Failed to open panel: {e}",
            )
            return False, False

    def _on_dock_visibility(self, visible):
        if self.toolbar_action is not None:
            self.toolbar_action.setChecked(visible)

    def toggle_dock(self, checked=False):
        print(f"[CartogenAi] toggle_dock(checked={checked})")
        ok, just_created = self._ensure_dock()
        if not ok:
            if self.toolbar_action is not None:
                self.toolbar_action.setChecked(False)
            return

        if just_created:
            # Already visible from addDockWidget -- just make sure it's on
            # top and the toolbar button reflects that, don't toggle it.
            self.dock_widget.show()
            self.dock_widget.raise_()
            if self.toolbar_action is not None:
                self.toolbar_action.setChecked(True)
            return

        if self.dock_widget.isVisible():
            self.dock_widget.hide()
        else:
            self.dock_widget.show()
            self.dock_widget.raise_()
