# -*- coding: utf-8 -*-
"""A per-project GeoPackage that keeps analysis outputs across Save and Reopen (rc7 smoke test F06).

Cartogen's analysis tools produce QGIS MEMORY layers. QGIS writes a memory layer's definition into the project file
but not its features, so after Save + load_project a service area that took ~44 minutes came back empty. The fix is the
standard QGIS one -- write the layer into a GeoPackage and point the layer at it ("Make permanent") -- done automatically
for analysis outputs, into one file per project: <project folder>/data/20_processed/cartogen_results.gpkg.

Design points (each is a deliberate answer to a risk, not a guess about QGIS):
- Every persist writes a NEW table (name + timestamp) and re-points the layer at it, rather than overwriting the table
  the layer has open: overwriting an open GeoPackage table can lock the file on Windows. Older tables for the same
  output are dropped afterwards, best effort, once nothing in the project uses them.
- The layer keeps its id, tree node and renderer: only its data source changes (QgsVectorLayer.setDataSource).
- Provenance (tool, source layers, time) goes into the layer's own QgsLayerMetadata abstract, which is stored in the
  project file, instead of being lost on conversion.
- An UNSAVED project has no folder to write into: nothing is written, and the caller is told so (persist_layer returns a
  reason) so the chat can ask the user to save the project first. No file is created in a surprise location.
- Needs only the GDAL/OGR that ships with QGIS. No network, no extra package.
"""
import os
import re
import time

try:
    from qgis.core import (
        QgsCoordinateTransformContext, QgsLayerMetadata, QgsProject, QgsVectorFileWriter,
    )
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

from ..logger import log_event

STORE_FILE_NAME = "cartogen_results.gpkg"
_TABLE_PREFIX_RE = re.compile(r"[^0-9A-Za-z_]+")


def store_path(project_file_name):
    """<project folder>/data/20_processed/cartogen_results.gpkg, or None for an unsaved project. Pure."""
    if not project_file_name:
        return None
    home = os.path.dirname(os.path.abspath(project_file_name))
    return os.path.join(home, "data", "20_processed", STORE_FILE_NAME)


def table_base(layer_name):
    """A GeoPackage-safe table name stem for a layer name. Pure."""
    stem = _TABLE_PREFIX_RE.sub("_", str(layer_name or "layer")).strip("_") or "layer"
    if stem[0].isdigit():
        stem = "t_" + stem
    return stem[:48]


def new_table_name(layer_name, now=None):
    """Unique per persist, so an open table is never overwritten. Pure given `now`."""
    stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(now if now is not None else time.time()))
    return f"{table_base(layer_name)}__{stamp}"


def is_persistable(layer):
    return bool(QGIS_AVAILABLE and layer is not None and hasattr(layer, "providerType")
                and layer.providerType() == "memory" and layer.isValid())


def provenance_abstract(tool, sources, now=None):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now if now is not None else time.time()))
    src = ", ".join(str(s) for s in (sources or [])) or "n/a"
    return f"Created by Cartogen AI tool '{tool}' at {stamp}. Source layers: {src}. Stored in {STORE_FILE_NAME}."


def persist_layer(layer, tool="analysis", sources=None, project=None):
    """Writes a memory layer into the project's results GeoPackage and re-points the layer at it.

    Returns {'persisted': True, 'path': ..., 'table': ...} or {'persisted': False, 'reason': ...}. Never raises: a failure
    to persist must not fail the analysis that produced the layer -- the layer simply stays temporary and the reason is
    reported."""
    if not QGIS_AVAILABLE:
        return {"persisted": False, "reason": "QGIS not available"}
    if not is_persistable(layer):
        return {"persisted": False, "reason": "not a memory layer"}
    project = project or QgsProject.instance()
    path = store_path(project.fileName())
    if path is None:
        return {"persisted": False, "reason": "the project has not been saved yet; save it to keep analysis results"}
    table = new_table_name(layer.name())
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.fileEncoding = "UTF-8"
        options.layerName = table
        action = getattr(QgsVectorFileWriter, "ActionOnExistingFile", None)
        create_or_overwrite = getattr(action, "CreateOrOverwriteLayer", None) if action is not None else None
        if create_or_overwrite is None:
            create_or_overwrite = getattr(QgsVectorFileWriter, "CreateOrOverwriteLayer", None)
        if create_or_overwrite is not None and os.path.exists(path):
            options.actionOnExistingFile = create_or_overwrite
        result = QgsVectorFileWriter.writeAsVectorFormatV3(layer, path, QgsCoordinateTransformContext(), options)
        error_code = result[0] if isinstance(result, (tuple, list)) else result
        no_error = getattr(getattr(QgsVectorFileWriter, "WriterError", None), "NoError", None)
        if no_error is None:
            no_error = getattr(QgsVectorFileWriter, "NoError", 0)
        if error_code != no_error:
            message = result[1] if isinstance(result, (tuple, list)) and len(result) > 1 else str(error_code)
            return {"persisted": False, "reason": f"writing the GeoPackage failed: {message}"}
        name = layer.name()
        layer.setDataSource(f"{path}|layername={table}", name, "ogr")
        if not layer.isValid():
            return {"persisted": False, "reason": "the written table could not be reopened"}
        md = QgsLayerMetadata()
        md.setTitle(name)
        md.setAbstract(provenance_abstract(tool, sources))
        layer.setMetadata(md)
        log_event("results_store", tag="Tools", tool=tool, status="persisted")
        return {"persisted": True, "path": path, "table": table}
    except Exception as e:
        log_event("results_store", tag="Tools", tool=tool, status="failed", error=True)
        return {"persisted": False, "reason": f"{type(e).__name__}: {e}"}
