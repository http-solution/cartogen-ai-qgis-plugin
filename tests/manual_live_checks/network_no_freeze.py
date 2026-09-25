# -*- coding: utf-8 -*-
"""Manual check that routing over the FULL Jordan road network (161,041 roads) no longer freezes QGIS.

Not part of the automated suite: it uses the Geofabrik Jordan extract (cached under %TEMP%, ~60 MB) and
one part takes about 5 minutes. Run with QGIS's Python:

    set QT_QPA_PLATFORM=offscreen
    "C:\\Program Files\\QGIS 4.2.2\\bin\\python-qgis.bat" -u tests\\manual_live_checks\\network_no_freeze.py

BUG-2026-09-25-2: on the GUI thread these calls took 292-572 s and QGIS showed "Not Responding". Now:
  Part A: a travel-time matrix is stopped after 30 s: it must return promptly, say it was cancelled, and
          the GUI event loop must have kept ticking (a 100 ms timer is the stand-in for the window).
  Part B: a full one-hour service area runs to completion with the GUI ticking throughout, and still
          reaches the same 46.4 km as the synchronous run did (tests/manual_live_checks/
          one_hour_travel_workflow.py)."""
import os
import sys
import tempfile
import time

SRC = os.environ.get("CARTOGEN_SRC", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))
sys.path.insert(0, SRC)
from qgis.core import (Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform,  # noqa: E402
                       QgsDistanceArea, QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer)
from qgis.PyQt.QtCore import QTimer  # noqa: E402

app = QgsApplication([], True)
app.initQgis()
sys.path.insert(0, os.path.join(QgsApplication.pkgDataPath(), "python", "plugins"))
from processing.core.Processing import Processing  # noqa: E402
Processing.initialize()
from cartogen_ai.core.agent import cancel_signal, local_data_loader as ldl  # noqa: E402
from cartogen_ai.core.agent.tools import logistics_tools as lt  # noqa: E402

print("QGIS", Qgis.QGIS_VERSION.split("-")[0], "| testing source:", SRC.replace(os.path.expanduser("~"), "~"))
results = []


def check(label, cond, detail=""):
    results.append(bool(cond))
    print(("PASS" if cond else "FAIL"), "-", label, "|", detail)


WEB_MERCATOR = QgsCoordinateReferenceSystem("EPSG:3857")
QgsProject.instance().setCrs(WEB_MERCATOR)
QgsProject.instance().setEllipsoid("NONE")
cache = os.path.join(tempfile.gettempdir(), "cartogen_jordan_e2e")
region = ldl.resolve_region(35.93, 31.95, cache)
loaded = ldl.load_layers(ldl.download_and_extract(region, cache), ["roads", "health_facilities"])
roads_name, fac_name = "OSM Roads (Jordan)", "Health Facilities (OSM, Jordan)"
print("network:", loaded["layers"][0]["count"], "roads |", loaded["layers"][1]["count"], "facilities")

origin = QgsVectorLayer("Point?crs=EPSG:3857&field=name:string", "Origin Location", "memory")
f = QgsFeature(origin.fields())
f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(3999682.0, 3756232.0)))
origin.dataProvider().addFeatures([f])
QgsProject.instance().addMapLayer(origin)

ticks = []
timer = QTimer()
timer.setInterval(100)
timer.timeout.connect(lambda: ticks.append(time.monotonic()))


def gaps():
    return [b - a for a, b in zip(ticks, ticks[1:])]


# ---- Part A: Stop after 30 s -------------------------------------------------------------------------
print("\n== Part A: travel_time_matrix, Stop pressed after 30 s ==")
statuses = []
t0 = time.monotonic()
cancel_signal.begin(should_stop=lambda: time.monotonic() - t0 > 30, status=statuses.append)
ticks.clear()
timer.start()
res = lt.travel_time_matrix("Origin Location", fac_name, roads_name, strategy="fastest", default_speed=50)
elapsed = time.monotonic() - t0
timer.stop()
cancel_signal.end()
print("returned after %.1f s (Stop was due at 30 s); GUI ticks: %d, worst gap %.0f ms" % (elapsed, len(ticks), max(gaps()) * 1000 if gaps() else -1))
print("progress messages:", len(statuses), "| last:", statuses[-1] if statuses else None)
check("Stop ended the analysis promptly", res.get("cancelled") and 30 <= elapsed < 40, "%.1f s" % elapsed)
check("the GUI kept ticking the whole time (no freeze)", len(ticks) > 0.8 * elapsed / 0.1 and max(gaps()) < 1.0,
      "%d ticks in %.0f s, worst gap %.0f ms" % (len(ticks), elapsed, max(gaps()) * 1000))
check("progress was reported to the user", len(statuses) >= 2 and "press Stop" in statuses[0], statuses[:1])
check("nothing was added to the project by the stopped run", not [n for n in QgsProject.instance().mapLayers().values()
                                                                    if "service_area" in n.name()])

# ---- Part B: a full one-hour service area, GUI ticking throughout ---------------------------------------
print("\n== Part B: one-hour service area, run to completion ==")
statuses.clear()
cancel_signal.begin(status=statuses.append)
ticks.clear()
timer.start()
t0 = time.monotonic()
sa = lt.calculate_service_area("Origin Location", roads_name, 1, strategy="fastest", default_speed=50)
elapsed = time.monotonic() - t0
timer.stop()
cancel_signal.end()
print("finished in %.0f s; GUI ticks: %d, worst gap %.0f ms; progress messages: %d" % (elapsed, len(ticks), max(gaps()) * 1000 if gaps() else -1, len(statuses)))
check("service area completed", sa.get("success") and sa.get("travel_cost_unit") == "hours", sa.get("error") or sa.get("travel_cost_unit"))
check("the GUI kept ticking the whole time (no freeze)", len(ticks) > 0.8 * elapsed / 0.1 and max(gaps()) < 1.0,
      "%d ticks in %.0f s, worst gap %.0f ms" % (len(ticks), elapsed, max(gaps()) * 1000))
if sa.get("layers_created"):
    wgs = QgsCoordinateReferenceSystem("EPSG:4326")
    da = QgsDistanceArea()
    da.setSourceCrs(wgs, QgsProject.instance().transformContext())
    da.setEllipsoid("WGS84")
    o = QgsCoordinateTransform(WEB_MERCATOR, wgs, QgsProject.instance()).transform(QgsPointXY(3999682.0, 3756232.0))
    hull = QgsProject.instance().mapLayersByName(sa["layers_created"][-1])[0]
    to_w = QgsCoordinateTransform(hull.crs(), wgs, QgsProject.instance())
    far = max(da.measureLine(o, to_w.transform(QgsPointXY(v.x(), v.y()))) for ft in hull.getFeatures() for v in ft.geometry().vertices())
    check("same 1-hour reach as the synchronous run (46.4 km)", abs(far / 1000 - 46.4) < 0.5, "%.1f km" % (far / 1000))

print("\n%d/%d passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
