"""Run by QGIS at start-up (qgis --code): enables the Cartogen plugin if it is installed and shows the smoke card dock. CARTOGEN_SMOKE_DIR names the package folder."""
import os
import sys

package = os.environ.get("CARTOGEN_SMOKE_DIR", "")
if package:
    sys.path.insert(0, os.path.join(package, "tools"))
    from qgis.PyQt.QtCore import QTimer

    def _go():
        import qgis.utils as qu
        try:
            if "cartogen_ai_plugin" not in qu.active_plugins:
                qu.loadPlugin("cartogen_ai_plugin")
                qu.startPlugin("cartogen_ai_plugin")
        except Exception as e:
            print(f"smoke: could not start the Cartogen plugin: {type(e).__name__}: {e}")
        import smoke_dock
        smoke_dock.show(package)

    QTimer.singleShot(4000, _go)           # after the main window and plugins are up
else:
    print("smoke: CARTOGEN_SMOKE_DIR is not set; run START_QGIS.bat")
