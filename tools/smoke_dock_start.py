"""Run by QGIS at start-up (qgis --code): enables the Cartogen plugin if it is installed and shows the smoke card dock. CARTOGEN_SMOKE_DIR names the package folder.
Every step is logged to results/dock_start.log and any failure (with traceback) to results/dock_errors.txt: a silent failure here left the 2026-11-20 run with no dock and no trace."""
import os
import sys

package = os.environ.get("CARTOGEN_SMOKE_DIR", "")
if package:
    sys.path.insert(0, os.path.join(package, "tools"))
    os.environ["CARTOGEN_LAYOUT_CHECK_DIR"] = os.path.join(package, "results", "outputs", "A1-layout-script")        # row A1 exports its pages here, inside the package folder
    from qgis.PyQt.QtCore import QTimer
    import smoke_cards as _cards

    _results = os.path.join(package, "results")
    _cards.start_log(_results, "smoke_dock_start.py ran; the dock is built in 4 s")

    def _go():
        try:
            import qgis.utils as qu
            try:
                if "cartogen_ai_plugin" not in qu.active_plugins:
                    qu.loadPlugin("cartogen_ai_plugin")
                    qu.startPlugin("cartogen_ai_plugin")
                _cards.start_log(_results, "Cartogen plugin active: " + str("cartogen_ai_plugin" in qu.active_plugins))
            except Exception as e:                  # the plugin failing must not stop the dock
                _cards.start_error(_results, "starting the Cartogen plugin", e)
            import smoke_dock
            smoke_dock.show(package)
        except Exception as e:                      # nothing may escape a Qt timer unseen
            _cards.start_error(_results, "building the dock", e)

    QTimer.singleShot(4000, _go)           # after the main window and plugins are up
else:
    print("smoke: CARTOGEN_SMOKE_DIR is not set; run START_QGIS.bat")
