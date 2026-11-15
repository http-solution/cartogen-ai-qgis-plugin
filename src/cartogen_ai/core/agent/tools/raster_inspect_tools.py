"""build_pyramids, raster_attribute_table and get_raster_value (PLAN-023 R10-4): what is in a raster, and making a big one draw fast.

* get_raster_value: the value of a raster at a coordinate (all bands or one), with the column and row of the cell, in the given CRS (default: the project's). It uses the same
  provider.sample reading as identify_at_point (R9-5).
* raster_attribute_table: the table that goes with a class raster (value, class name, colour, count ...), read through GDAL; most rasters have none and the reply says so. At most 200 rows.
* build_pyramids: overview levels in a sidecar .ovr file NEXT TO the raster (GDAL opens the raster read-only, so the raster is never rewritten). When an .ovr already exists, rebuilding is
  a PREVIEW_REQUIRED confirm (the existing file is replaced). A raster that already has pyramids inside the file is left alone. The count of overview levels is read back. See pyramid_ops.py.

Written without a QGIS install; tests/test_raster_inspect_tools_live.py is their first execution in CI."""
import os

from . import pyramid_ops as po
from .attribute_edit_tools import preview
from .identify_tool import _raster_values
from .registry import register_tool

try:
    from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsPointXY, QgsProject, QgsRasterLayer
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

GDAL_METHODS = {"average": "AVERAGE", "nearest": "NEAREST", "gauss": "GAUSS", "cubic": "CUBIC", "mode": "MODE"}
RAT_TYPES = {0: "integer", 1: "real", 2: "string"}


def _raster(layer_name):
    """(layer, error): a raster layer by name. Needs QGIS."""
    matches = QgsProject.instance().mapLayersByName(str(layer_name)) if QGIS_AVAILABLE else []
    if not matches or not isinstance(matches[0], QgsRasterLayer):
        return None, {"error": f"Raster layer '{layer_name}' not found."}
    return matches[0], None


def _file_path(layer):
    """The local file behind a raster layer, or None when it is a web, virtual or in-memory raster. Needs QGIS."""
    path = str(layer.source()).split("|")[0]
    return path if os.path.isfile(path) else None


def _geotransform(layer):
    ext = layer.extent()
    return (ext.xMinimum(), layer.rasterUnitsPerPixelX(), 0.0, ext.yMaximum(), 0.0, -layer.rasterUnitsPerPixelY())


@register_tool(
    "get_raster_value",
    "Read the value of a raster layer at a coordinate: every band (or only `band`) and the column and row of the cell it falls in. x and y are in `crs` (default: the project CRS). A point "
    "outside the raster is reported, and a NoData cell comes back as null. Read-only. To look at vector layers and rasters together at a point use identify_at_point.",
    {"type": "object", "properties": {
        "layer_name": {"type": "string", "description": "The raster layer."},
        "x": {"type": "number", "description": "X (longitude or easting) in `crs`."},
        "y": {"type": "number", "description": "Y (latitude or northing) in `crs`."},
        "band": {"type": "integer", "description": "One band number, 1-based (default: all bands)."},
        "crs": {"type": "string", "description": "The CRS of x and y, for example EPSG:4326 (default: the project CRS)."}},
     "required": ["layer_name", "x", "y"]},
    keywords=["raster value at", "value of the raster at", "cell value at", "pixel value at", "what is the pixel value", "read the raster at a point", "elevation at a coordinate", "value of the dem at"],
)
def get_raster_value(layer_name, x, y, band=None, crs=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    from .identify_ops import check_request
    problem = check_request(x, y)
    if problem:
        return {"error": problem}
    layer, err = _raster(layer_name)
    if err:
        return err
    if band is not None and (isinstance(band, bool) or not isinstance(band, int) or not 1 <= band <= layer.bandCount()):
        return {"error": f"band must be a whole number from 1 to {layer.bandCount()} for '{layer_name}'."}
    project = QgsProject.instance()
    in_crs = QgsCoordinateReferenceSystem(str(crs)) if crs else project.crs()
    if not in_crs.isValid():
        return {"error": f"'{crs}' is not a coordinate system QGIS knows (for example EPSG:4326)." if crs else "The project has no coordinate system; give crs, for example EPSG:4326."}
    point = QgsPointXY(float(x), float(y))
    if layer.crs().isValid() and layer.crs() != in_crs:
        point = QgsCoordinateTransform(in_crs, layer.crs(), project).transform(point)
    cell = po.cell_index(_geotransform(layer), point.x(), point.y(), layer.width(), layer.height())
    if cell is None:
        return {"success": True, "layer_name": layer_name, "inside": False, "message": "The point is outside this raster.", "point_in_layer_crs": [round(point.x(), 6), round(point.y(), 6)]}
    values = _raster_values(layer, point)
    if band is not None:
        name = layer.bandName(band) or str(band)
        values = {name: values.get(name)} if values else values
    return {"success": True, "layer_name": layer_name, "inside": True, "column": cell[0], "row": cell[1], "values": values,
            "point_in_layer_crs": [round(point.x(), 6), round(point.y(), 6)], "nodata": bool(values) and all(v is None for v in values.values())}


def _rat_cell(table, row, col, kind):
    """One cell of a GDAL raster attribute table as an int, a float or text. Needs GDAL."""
    if kind == "integer":
        return table.GetValueAsInt(row, col)
    return table.GetValueAsDouble(row, col) if kind == "real" else table.GetValueAsString(row, col)


@register_tool(
    "raster_attribute_table",
    "Read the attribute table of a classified raster (value, class name, colour, pixel count and so on), the table QGIS shows under Layer Properties > Attribute Table. Many rasters have none "
    "and the reply says so. At most 200 rows are returned and the reply says when there are more. Read-only.",
    {"type": "object", "properties": {
        "layer_name": {"type": "string", "description": "The raster layer (a file)."},
        "band": {"type": "integer", "description": "The band, 1-based (default 1)."}},
     "required": ["layer_name"]},
    keywords=["raster attribute table", "attribute table of the raster", "class table of the raster", "classes of the raster", "raster legend table", "rat of the raster"],
)
def raster_attribute_table(layer_name, band=1):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer, err = _raster(layer_name)
    if err:
        return err
    if isinstance(band, bool) or not isinstance(band, int) or not 1 <= band <= layer.bandCount():
        return {"error": f"band must be a whole number from 1 to {layer.bandCount()} for '{layer_name}'."}
    path = _file_path(layer)
    if path is None:
        return {"error": f"'{layer_name}' is not a local raster file, so its attribute table cannot be read."}
    from osgeo import gdal
    dataset = gdal.Open(path)
    if dataset is None:
        return {"error": "GDAL could not open the raster file."}
    table = dataset.GetRasterBand(band).GetDefaultRAT()
    if table is None or table.GetColumnCount() == 0:
        return {"success": True, "layer_name": layer_name, "band": band, "has_attribute_table": False, "message": "This raster has no attribute table (many class rasters do not)."}
    columns = [table.GetNameOfCol(i) for i in range(table.GetColumnCount())]
    kinds = [RAT_TYPES.get(table.GetTypeOfCol(i), "string") for i in range(len(columns))]
    total = table.GetRowCount()
    rows = [[_rat_cell(table, r, c, kinds[c]) for c in range(len(columns))] for r in range(min(total, po.ROW_CAP))]
    result = po.rat_table(columns, rows)
    result["total_rows"] = total
    result["truncated"] = total > po.ROW_CAP
    return {"success": True, "layer_name": layer_name, "band": band, "has_attribute_table": True, "column_types": dict(zip(columns, kinds, strict=True)), **result}


def _overview_count(path):
    """Number of overview levels GDAL sees for band 1 of the raster at `path` (an .ovr beside it counts), or None when it cannot be opened. Needs GDAL."""
    from osgeo import gdal
    dataset = gdal.Open(path)
    return None if dataset is None else dataset.GetRasterBand(1).GetOverviewCount()


@register_tool(
    "build_pyramids",
    "Build pyramids (overviews) for a raster layer so a big raster draws fast when zoomed out: smaller copies are written to a sidecar .ovr file NEXT TO the raster, which itself is never "
    "rewritten. levels is a list such as [2, 4, 8] (default: halving while the smaller side stays at least 256 cells; a raster under 512 cells needs none); method is average (default, for "
    "continuous data), nearest, gauss, cubic or mode (for classified rasters). If an .ovr file already exists a preview asks before it is replaced. The number of levels is read back.",
    {"type": "object", "properties": {
        "layer_name": {"type": "string", "description": "The raster layer (a local file)."},
        "levels": {"type": "array", "items": {"type": "integer"}, "description": "Overview factors, increasing, each 2 or more (default: chosen from the raster's size)."},
        "method": {"type": "string", "enum": list(po.METHODS), "description": "Resampling: average (default), nearest, gauss, cubic or mode."}},
     "required": ["layer_name"]},
    keywords=["build pyramids", "build overviews", "pyramids for the raster", "make the raster draw faster", "speed up the raster", "raster is slow to draw", "overviews for the raster", "create overviews"],
)
def build_pyramids(layer_name, levels=None, method="average", confirmed=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer, err = _raster(layer_name)
    if err:
        return err
    path = _file_path(layer)
    if path is None:
        return {"error": f"'{layer_name}' is not a local raster file, so pyramids cannot be built next to it."}
    wanted, problem = po.check_build(levels, method, layer.width(), layer.height())
    if problem:
        return {"error": problem}
    sidecar = path + ".ovr"
    existing = _overview_count(path)
    if existing is None:
        return {"error": "GDAL could not open the raster file."}
    if existing and not os.path.exists(sidecar):
        return {"success": True, "layer_name": layer_name, "built": False, "overview_levels": existing, "message": f"This raster already has {existing} pyramid level(s) inside the file; nothing was built."}
    if os.path.exists(sidecar) and not confirmed:
        arguments = {"layer_name": layer_name, "levels": wanted, "method": str(method).strip().lower()}
        return preview("build_pyramids", arguments, f"Replace the existing pyramids file {os.path.basename(sidecar)} ({existing} level(s)) with levels {wanted} ({str(method).strip().lower()}). The raster is not changed.",
                       f"gdal.Open('{os.path.basename(path)}').BuildOverviews('{GDAL_METHODS[str(method).strip().lower()]}', {wanted})   # writes {os.path.basename(sidecar)}")
    from osgeo import gdal
    if os.path.exists(sidecar):
        os.remove(sidecar)
    dataset = gdal.Open(path, gdal.GA_ReadOnly)
    if dataset is None:
        return {"error": "GDAL could not open the raster file."}
    code = dataset.BuildOverviews(GDAL_METHODS[str(method or "average").strip().lower()], wanted)
    dataset = None
    if code != 0:
        return {"error": f"GDAL could not build the pyramids (code {code}); the folder may be read-only."}
    layer.dataProvider().reloadData()
    layer.triggerRepaint()
    return {"success": True, "layer_name": layer_name, "built": True, "levels": wanted, "method": str(method or "average").strip().lower(), "overview_levels_now": _overview_count(path),
            "sidecar_file": sidecar, "note": "The raster file itself was not changed; the pyramids are in the .ovr file beside it (keep the two together when copying)."}
