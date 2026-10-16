"""Runs ONE mesh-family algorithm in its own process (python -m tests._mesh_probe <alg_id>) and prints `RESULT <json>`; the same idea as
tests/_grass_probe.py. The mesh is a 3 x 3 node grid of 8 triangles written as a .2dm file, with a bed-elevation dataset group.
Written without a QGIS install: CI's first run is its first execution."""
import json
import os
import sys
import tempfile

from tests._grass_probe import grass_params

MESH = "\n".join(["MESH2D"] + [f"E3T {i} {a} {b} {c} 1" for i, (a, b, c) in enumerate(
    [(1, 2, 4), (2, 5, 4), (2, 3, 5), (3, 6, 5), (4, 5, 7), (5, 8, 7), (5, 6, 8), (6, 9, 8)], 1)]
    + [f"ND {n} {(n - 1) % 3} {(n - 1) // 3} {float(n)}" for n in range(1, 10)]) + "\n"


def mesh_params(algorithm):
    params = grass_params(algorithm, "unused")
    for p in algorithm.parameterDefinitions():
        if p.isDestination():
            continue
        if p.type() == "mesh":
            params[p.name()] = "mesh1"
        elif p.type() == "meshdatasetgroups":
            params[p.name()] = [0]
        elif p.type() == "distance" and not _optional(p):
            params[p.name()] = 0.5
        elif p.type() == "meshdatasettime":
            params.pop(p.name(), None)   # a time-range object cannot be passed as plain JSON; the algorithm's own default is used
    return params


def _optional(parameter):
    from tests._geometry_probe import _is_optional
    return _is_optional(parameter)


def main(alg_id):
    from qgis.core import QgsApplication, QgsCoordinateReferenceSystem, QgsMeshLayer, QgsProject
    from tests.test_network_units_live import _boot
    why = _boot()
    if why:
        print("RESULT " + json.dumps({"ok": False, "error": "boot: " + why}), flush=True)
        return
    path = os.path.join(tempfile.mkdtemp(), "m.2dm")
    with open(path, "w") as fh:
        fh.write(MESH)
    mesh = QgsMeshLayer(path, "mesh1", "mdal")
    mesh.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    if not mesh.isValid():
        print("RESULT " + json.dumps({"ok": False, "error": "the test mesh did not load"}), flush=True)
        return
    QgsProject.instance().addMapLayer(mesh)
    from cartogen_ai.core.agent.tools.processing_allowlist_tools import run_allowlisted_processing_algorithm
    algorithm = QgsApplication.processingRegistry().algorithmById(alg_id)
    if algorithm is None:
        print("RESULT " + json.dumps({"ok": False, "error": "not in the QGIS registry"}), flush=True)
        return
    result = run_allowlisted_processing_algorithm(alg_id, mesh_params(algorithm), new_layer_name="out")
    if result.get("success"):
        print("RESULT " + json.dumps({"ok": True, "message": str(result.get("message", ""))[:120]}), flush=True)
    else:
        print("RESULT " + json.dumps({"ok": False, "error": str(result.get("error"))[:300]}), flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
