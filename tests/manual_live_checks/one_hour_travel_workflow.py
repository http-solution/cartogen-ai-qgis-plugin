# -*- coding: utf-8 -*-
"""Manual end-to-end check of "Health facilities beyond one hour's travel 3999682,3756232" with REAL data.

Not part of the automated suite: it downloads the Geofabrik Jordan OpenStreetMap extract (~60 MB, cached
under %TEMP%) and runs the plugin's own tools on it in real QGIS. Run with QGIS's Python:

    set QT_QPA_PLATFORM=offscreen
    "C:\\Program Files\\QGIS 4.2.2\\bin\\python-qgis.bat" tests\\manual_live_checks\\one_hour_travel_workflow.py

What it checks (BUG-2026-09-24-5, docs/BUG_TRACKER.md): the tools work in real metres/hours whatever the layers'
CRS or the project's ellipsoid. The origin is typed the way the user typed it: Web Mercator metres. Every
route cost is compared with an independent geodesic straight-line distance: a road route can never be shorter
than that, and at 50 km/h a cost in hours implies a distance we can check against it.

Environment: CARTOGEN_SRC (source folder to test; default this repo's src), CARTOGEN_PROJECT_ELLIPSOID
("NONE" by default, the worst case)."""
import os
import sys
import tempfile
import time

SRC = os.environ.get("CARTOGEN_SRC", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))
sys.path.insert(0, SRC)
from qgis.core import (Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform,  # noqa: E402
                       QgsDistanceArea, QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer)

app = QgsApplication([], True)
app.initQgis()
sys.path.insert(0, os.path.join(QgsApplication.pkgDataPath(), "python", "plugins"))
from processing.core.Processing import Processing  # noqa: E402
Processing.initialize()
from cartogen_ai.core.agent import local_data_loader as ldl  # noqa: E402
from cartogen_ai.core.agent.tools import logistics_tools as lt  # noqa: E402

print("QGIS", Qgis.QGIS_VERSION.split("-")[0], "| testing source:", SRC.replace(os.path.expanduser("~"), "~"))
results = []


def check(label, cond, detail=""):
    results.append(bool(cond))
    print(("PASS" if cond else "FAIL"), "-", label, "|", detail)


ELLIPSOID = os.environ.get("CARTOGEN_PROJECT_ELLIPSOID", "NONE")
WEB_MERCATOR = QgsCoordinateReferenceSystem("EPSG:3857")
QgsProject.instance().setCrs(WEB_MERCATOR)
QgsProject.instance().setEllipsoid(ELLIPSOID)
print("project CRS EPSG:3857, ellipsoid:", ELLIPSOID)

# --- data: the real Jordan extract, loaded the way the plugin's "download local data" step does ----
cache = os.path.join(tempfile.gettempdir(), "cartogen_jordan_e2e")
t = time.time()
region = ldl.resolve_region(35.93, 31.95, cache)
check("Geofabrik region found for the origin", region.get("id") == "jordan", (region.get("name"), region.get("size_bytes")))
result = ldl.download_and_extract(region, cache)
print("extract ready in %.0fs" % (time.time() - t))
loaded = ldl.load_layers(result, ["roads", "health_facilities"])
for lyr in loaded["layers"]:
    print("  loaded:", lyr["name"], lyr["count"], "features")
check("roads and health facilities loaded", len(loaded["layers"]) == 2 and not loaded["errors"], loaded["errors"])
roads_name = "OSM Roads (Jordan)"
fac_name = "Health Facilities (OSM, Jordan)"

# --- the user's origin: Web Mercator metres, exactly as typed ----------------------------------------
ox, oy = 3999682.0, 3756232.0
origin = QgsVectorLayer("Point?crs=EPSG:3857&field=name:string", "Origin Location", "memory")
f = QgsFeature(origin.fields())
f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(ox, oy)))
f.setAttributes(["Origin Site"])
origin.dataProvider().addFeatures([f])
QgsProject.instance().addMapLayer(origin)
wgs = QgsCoordinateReferenceSystem("EPSG:4326")
olon_lat = QgsCoordinateTransform(WEB_MERCATOR, wgs, QgsProject.instance()).transform(QgsPointXY(ox, oy))
print("origin = %.5f N, %.5f E (Amman)" % (olon_lat.y(), olon_lat.x()))

da = QgsDistanceArea()
da.setSourceCrs(wgs, QgsProject.instance().transformContext())
da.setEllipsoid("WGS84")

# --- 1. travel time from the origin to every health facility (fastest, 50 km/h) ------------------------
t = time.time()
tm = lt.travel_time_matrix("Origin Location", fac_name, roads_name, strategy="fastest", default_speed=50)
print("travel_time_matrix took %.0fs" % (time.time() - t))
check("travel_time_matrix succeeded and states its unit", tm.get("success") and tm.get("cost_unit") == "hours", tm.get("error") or tm.get("cost_unit"))

fac = QgsProject.instance().mapLayersByName(fac_name)[0]
roads_crs = QgsProject.instance().mapLayersByName(roads_name)[0].crs()
to_wgs = QgsCoordinateTransform(roads_crs, wgs, QgsProject.instance())
costs, straight = {}, {}
for key, value in list(tm["matrix"].values())[0].items():
    # the matrix is keyed by each destination's coordinates in the NETWORK's CRS: "x, y"
    try:
        hours = float(value)
        x, y = (float(v) for v in key.split(","))
    except (TypeError, ValueError):
        continue
    p = to_wgs.transform(QgsPointXY(x, y))
    costs[key] = hours
    straight[key] = da.measureLine(QgsPointXY(olon_lat.x(), olon_lat.y()), QgsPointXY(p.x(), p.y()))
print("facilities:", fac.featureCount(), "| with a route:", len(costs))
check("a route cost for most facilities", len(costs) >= 0.5 * fac.featureCount(), "%d of %d" % (len(costs), fac.featureCount()))

# route length implied by hours x 50 km/h, vs the straight line to the same facility
ratios = sorted(costs[k] * 50000.0 / straight[k] for k in costs if straight[k] > 500)
if ratios:
    print("route length / straight line: min %.2f  median %.2f  max %.2f  (n=%d)" % (ratios[0], ratios[len(ratios) // 2], ratios[-1], len(ratios)))
check("no route is shorter than the straight line (units are real)", ratios and ratios[0] >= 0.95, "min ratio %.2f" % (ratios[0] if ratios else -1))
check("typical road/straight-line ratio is plausible (1.0 to 2.5)", ratios and 1.0 <= ratios[len(ratios) // 2] <= 2.5, "median %.2f" % (ratios[len(ratios) // 2] if ratios else -1))

within = sorted(k for k, h in costs.items() if h <= 1.0)
beyond = sorted(k for k, h in costs.items() if h > 1.0)
print("within one hour: %d | beyond one hour: %d" % (len(within), len(beyond)))
check("the one-hour split is meaningful (some inside, some beyond)", within and beyond, "%d inside / %d beyond" % (len(within), len(beyond)))
if beyond:
    far = max(costs[k] for k in beyond)
    print("farthest facility by road: %.1f hours" % far)

# --- 2. a one-hour service area around the origin ---------------------------------------------------------
t = time.time()
sa = lt.calculate_service_area("Origin Location", roads_name, 1, strategy="fastest", default_speed=50)
print("calculate_service_area took %.0fs" % (time.time() - t))
check("service area built and states its unit", sa.get("success") and sa.get("travel_cost_unit") == "hours", sa.get("error") or sa.get("travel_cost_unit"))
if sa.get("layers_created"):
    hull = QgsProject.instance().mapLayersByName(sa["layers_created"][-1])[0]
    farthest = 0.0
    to_w = QgsCoordinateTransform(hull.crs(), wgs, QgsProject.instance())
    for feat in hull.getFeatures():
        for v in feat.geometry().vertices():
            p = to_w.transform(QgsPointXY(v.x(), v.y()))
            farthest = max(farthest, da.measureLine(QgsPointXY(olon_lat.x(), olon_lat.y()), QgsPointXY(p.x(), p.y())))
    print("farthest point of the 1-hour reach: %.1f km straight-line from the origin" % (farthest / 1000))
    # 1 hour at 50 km/h is 50 km of road: the reach must be 10-50 km away in a straight line
    check("1-hour reach extends 10-50 km (50 km of road at 50 km/h)", 10000 <= farthest <= 50500, "%.1f km" % (farthest / 1000))

print("\n%d/%d passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
