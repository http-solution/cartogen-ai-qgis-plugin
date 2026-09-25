# -*- coding: utf-8 -*-
"""Manual check that clipping the road network to a service area's reach is exact AND faster, on the REAL
Jordan network (161,041 roads).

Not part of the automated suite: the comparisons route over the FULL network, which takes about 5 minutes
each. Run with QGIS's Python:

    set QT_QPA_PLATFORM=offscreen
    "C:\\Program Files\\QGIS 4.2.2\\bin\\python-qgis.bat" -u tests\\manual_live_checks\\network_clip_real.py

For each case the service area is computed twice, clipped (as the tool now does) and over the whole network
(clipping switched off), and the two must have identical geometry. BUG-2026-09-25-2."""
import os
import sys
import tempfile
import time
from unittest.mock import patch

SRC = os.environ.get("CARTOGEN_SRC", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))
sys.path.insert(0, SRC)
from qgis.core import (Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry, QgsPointXY,  # noqa: E402
                       QgsProject, QgsVectorLayer)

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


QgsProject.instance().setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
QgsProject.instance().setEllipsoid("NONE")
cache = os.path.join(tempfile.gettempdir(), "cartogen_jordan_e2e")
region = ldl.resolve_region(35.93, 31.95, cache)
loaded = ldl.load_layers(ldl.download_and_extract(region, cache), ["roads"])
roads = "OSM Roads (%s)" % region["name"]
print("network:", loaded["layers"][0]["count"], "roads")

CASES = [
    ("Amman, 3 km by road", (35.92975, 31.94606), dict(travel_cost=3000)),
    ("Irbid, 3 km by road", (35.85, 32.5556), dict(travel_cost=3000)),
    ("Amman, 12 min at 50 km/h (10 km)", (35.92975, 31.94606), dict(travel_cost=0.2, strategy="fastest", default_speed=50)),
]


def wkts(result):
    layers = [QgsProject.instance().mapLayersByName(n)[0] for n in result["layers_created"] if "_lines_" in n]
    return sorted(f.geometry().asWkt(6) for lyr in layers for f in lyr.getFeatures())


def drop_service_areas():
    QgsProject.instance().removeMapLayers([lyr.id() for lyr in QgsProject.instance().mapLayers().values() if "service_area" in lyr.name()])


for label, (lon, lat), kw in CASES:
    print("\n==", label, "==")
    for lyr in QgsProject.instance().mapLayersByName("origin"):
        QgsProject.instance().removeMapLayer(lyr.id())
    origin = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string", "origin", "memory")
    f = QgsFeature(origin.fields())
    f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
    origin.dataProvider().addFeatures([f])
    QgsProject.instance().addMapLayer(origin)

    t = time.time()
    clipped = lt.calculate_service_area("origin", roads, **kw)
    t_clip = time.time() - t
    a = wkts(clipped)
    drop_service_areas()
    info = clipped.get("network_clipping") or {}
    print("clipped: %.1f s, routed over %s of %s roads, %d line features" % (t_clip, info.get("roads_routed_max"), info.get("roads_full"), len(a)))

    t = time.time()
    with patch.object(lt, "_clip_network_to_reach", side_effect=lambda n, c, r: (n, {"applied": False})):
        full = lt.calculate_service_area("origin", roads, **kw)
    t_full = time.time() - t
    b = wkts(full)
    drop_service_areas()
    print("full:    %.1f s over all roads, %d line features" % (t_full, len(b)))
    check("%s: identical geometry" % label, clipped.get("success") and full.get("success") and a == b and len(a) > 0,
          "%d features each" % len(a))
    check("%s: faster (%.0fx)" % (label, t_full / max(t_clip, 0.1)), t_clip < t_full, "%.1f s vs %.1f s" % (t_clip, t_full))
    check("%s: the clip was applied" % label, bool(info), info.get("roads_routed_max"))

print("\n%d/%d passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
