# -*- coding: utf-8 -*-
"""
Renamed from cartogen_ai.py (see that file's own MOVED stub for why): a file
literally named cartogen_ai.py at the plugin root collided with the
cartogen_ai.core namespace package under src/. Both the repo root and src/
end up on sys.path (see __init__.py's bootstrap comment), and when Python
resolves the top-level name "cartogen_ai" it finds this regular module before
it finishes collecting src/cartogen_ai/ as a namespace portion -- a regular
module/package anywhere on sys.path always wins over a namespace portion,
regardless of sys.path order. Confirmed live: `python -m unittest discover`
failed 31 tests importing `cartogen_ai.core.agent.*` because "cartogen_ai"
resolved to this file (then its qgis.PyQt import failed, since qgis isn't
installed outside a real QGIS session) instead of the namespace package.
Renaming this file is what fixes it -- see docs/archive/MULTITIER_REPO_ARCHITECTURE_SPEC.md
§3 for the full writeup, and docs/BUG_TRACKER.md for the incident entry.
"""
import os.path
import re
import traceback

from qgis.PyQt.QtCore import Qt, QCoreApplication, QLocale, QTranslator, QTimer
from qgis.PyQt.QtGui import QIcon

try:
    from qgis.PyQt.QtGui import QAction
except ImportError:
    from qgis.PyQt.QtWidgets import QAction

from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout

from qgis.core import QgsSettings, QgsProject

SETTINGS_KEY = "cartogen_ai/api_key"
HELP_LAST_SHOWN_VERSION_KEY = "cartogen_ai/help_last_shown_version"


def _dock_area_right():
    area = getattr(Qt, "RightDockWidgetArea", None)
    if area is not None:
        return area
    return Qt.DockWidgetArea.RightDockWidgetArea


def _read_plugin_version(plugin_dir):
    """Mirrors plugin_upload.py's get_plugin_version() exactly (duplicated, not
    imported -- plugin_upload.py is itself excluded from the release zip by
    EXCLUDE_FILES, so it may not be present at runtime; same small-helper-per-file
    convention this codebase already uses for _find_layer_by_name). Read at runtime
    rather than hardcoded so the menu label can never drift from metadata.txt."""
    metadata_path = os.path.join(plugin_dir, "metadata.txt")
    if os.path.exists(metadata_path):
        with open(metadata_path, "r", encoding="utf-8") as f:
            for line in f:
                match = re.match(r"^version\s*=\s*(.+)$", line.strip())
                if match:
                    return match.group(1).strip()
    return "0.1.0"


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
        self._help_dialog = None
        self._agent = None
        self._agent_key = None

    def tr(self, message):
        return QCoreApplication.translate("CartogenAi", message)

    def initGui(self):
        print("[CartogenAi] initGui()")
        # icon.svg -- a copy of branding/cartogen-mark.svg, the actual brand mark, not the flat
        # icon.png this replaced. Deliberately copied to the plugin ROOT rather than referencing
        # branding/ directly: plugin_upload.py's EXCLUDE_DIRS excludes the whole branding/
        # folder from the release zip (the guidelines HTML/lockup SVGs genuinely have no
        # runtime function) -- pointing this at branding/cartogen-mark.svg would have silently
        # shipped a plugin with no toolbar icon at all, since QIcon() on a missing path just
        # produces an empty icon rather than raising. icon.svg has a real runtime function
        # (unlike the rest of branding/), so it ships from the root like icon.png always has.
        # Qt loads SVG natively via its SVG icon engine (scales cleanly at any toolbar/HiDPI
        # size). UI/chat redesign workstream, 2026-09-12.
        icon_path = os.path.join(self.plugin_dir, "icon.svg")
        action = QAction(QIcon(icon_path), self.tr("Cartogen AI"), self.iface.mainWindow())
        action.setCheckable(True)
        action.triggered.connect(self.toggle_dock)
        self.iface.addToolBarIcon(action)
        self.iface.addPluginToMenu(self.menu, action)
        self.actions.append(action)
        self.toolbar_action = action
        print("[CartogenAi] toolbar action installed")

        # Help moved here from a permanent 3rd dock tab, per a 2026-09-12 real-session user
        # report: a reference document doesn't need to occupy dock space at all times. The
        # version number itself lives ONLY inside the Help dialog's own content (see
        # show_help() / help_tab_widget.py) -- an earlier version of this also put a disabled
        # "Cartogen AI vX.Y.Z" entry directly in this menu, but direct follow-up feedback the
        # same day said that was one place too many; removed rather than kept as a second,
        # redundant spot.
        help_action = QAction(self.tr("Help"), self.iface.mainWindow())
        help_action.triggered.connect(self.show_help)
        self.iface.addPluginToMenu(self.menu, help_action)
        self.actions.append(help_action)

        # The agent instance and dock widget are cached/reused across QGIS
        # project switches (see _get_agent()), so without this the chat panel
        # would keep showing the previous project's conversation after the
        # user opens a different .qgz. QgsProject.instance() is a singleton,
        # so it's safe to connect once here.
        project = QgsProject.instance()
        project.readProject.connect(self._on_project_changed)
        project.cleared.connect(self._on_project_changed)

        # Deferred rather than called directly here: initGui() runs during QGIS's own plugin
        # load sequence, and popping a modal dialog synchronously inside it risks competing
        # with whatever QGIS itself is still doing at that exact moment. QTimer.singleShot(0)
        # runs it on the next pass of the Qt event loop instead, once QGIS has finished
        # settling -- the same "defer heavy/UI work out of initGui()" caution this codebase
        # already follows elsewhere.
        QTimer.singleShot(0, self._maybe_show_first_use_dialogs)

    def _maybe_show_first_use_dialogs(self):
        """First-use onboarding (role/experience/communication-style profile, real-session
        feature request 2026-09-12) plus Help auto-show (first use, and once again after any
        version update -- clarified via AskUserQuestion the same day). Onboarding runs first
        (a brief, one-time "who are you" moment) and only ever once; Help re-shows on every
        version bump, since that's meant as a lightweight "what's available" refresher, not a
        one-time gate."""
        from cartogen_ai.core.agent import onboarding_profile
        if not onboarding_profile.is_onboarding_completed():
            from cartogen_ai.core.ui.onboarding_dialog import OnboardingDialog
            OnboardingDialog(self.iface.mainWindow()).exec()

        settings = QgsSettings()
        current_version = _read_plugin_version(self.plugin_dir)
        last_shown_version = settings.value(HELP_LAST_SHOWN_VERSION_KEY, "")
        if last_shown_version != current_version:
            self.show_help()
            settings.setValue(HELP_LAST_SHOWN_VERSION_KEY, current_version)

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
            from cartogen_ai.core.agent.scheduler import get_scheduler
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

        if self._help_dialog is not None:
            try:
                self._help_dialog.close()
                self._help_dialog.deleteLater()
            except Exception as e:
                print(f"[CartogenAi] closing Help dialog failed: {e}")
            self._help_dialog = None

        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        self.actions = []

    def _get_agent(self):
        from cartogen_ai.core.agent.auth import CredentialManager
        settings = QgsSettings()
        provider = settings.value("cartogen_ai/provider", "openrouter")
        key = CredentialManager.get_credential(provider)
        agent_hash = f"{provider}_{key}"

        if self._agent is None or getattr(self, "_agent_key", None) != agent_hash:
            try:
                from cartogen_ai.core.agent.agent import CartogenAi as AgentCore
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
            from cartogen_ai.core.ui.dock_widget import CartogenAiDockWidget
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

    def show_help(self):
        """Opens Help in its own dialog rather than the dock -- independent of whether the
        dock has ever been created, and of the dock's own lifecycle (a dock the user has
        hidden shouldn't need to be shown just to read Help). Non-modal (exec() would block
        the rest of QGIS) and reused across clicks rather than rebuilt each time, matching
        how the toolbar toggle/dock_widget pattern above avoids recreating widgets."""
        if self._help_dialog is None:
            from cartogen_ai.core.ui.help_tab_widget import HelpTabWidget
            version = _read_plugin_version(self.plugin_dir)
            dialog = QDialog(self.iface.mainWindow())
            dialog.setWindowTitle(self.tr("Cartogen AI Help"))
            dialog.resize(520, 560)
            layout = QVBoxLayout(dialog)
            layout.addWidget(HelpTabWidget(parent=dialog, version=version))
            self._help_dialog = dialog
        self._help_dialog.show()
        self._help_dialog.raise_()
        self._help_dialog.activateWindow()

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
