"""From-to change matrix between two classified rasters (PLAN-023 R3-4): cross-tabulation, hectares, gain, loss, net and persistence.

Pure numpy and plain Python, no QGIS and no GDAL: the known answers are checked offline.

For two class rasters A (before) and B (after) over the cells valid in both:
  matrix[i][j]   = number of cells of class i in A that are class j in B (rows = from, columns = to)
  persistence i  = matrix[i][i]
  loss i         = sum of row i - persistence i      (cells that left class i)
  gain i         = sum of column i - persistence i   (cells that joined class i)
  net i          = gain i - loss i
Known answer (the test): A = [[1, 1], [2, 2]], B = [[1, 2], [2, 2]] gives the matrix [[1, 1], [0, 2]]; class 1 lost 1 cell and class 2 gained 1 cell.

Hectares: a projected raster has one cell area (pixel width x height in metres, from the CRS's linear unit). A geographic raster's cell area depends on latitude, so each
row gets its own area from the sphere with the WGS84 authalic radius (6,371,007.2 m): area = R^2 x delta_longitude x |sin lat_a - sin lat_b|, for the row's two edge latitudes.
That is an approximation of the ellipsoidal area, not the ellipsoidal area itself; the result says so. A CRS that is neither projected nor geographic gives counts only.

Class values must be whole numbers (a land-cover raster); a continuous raster has to be reclassified first. At most 50 classes."""
import math

MAX_CLASSES = 50
AUTHALIC_RADIUS_M = 6371007.2
M2_PER_HA = 10_000.0


def _np():
    import numpy as np
    return np


def parse_classes(classes):
    """({value: name}, error text or None) from the `classes` argument: a dict {value: name} (keys may be strings), or a list of {'value', 'name'} dicts, or
    None for no names. Names are trimmed and limited to 60 characters. Pure."""
    if classes in (None, "", [], {}):
        return {}, None
    pairs = []
    if isinstance(classes, dict):
        pairs = list(classes.items())
    elif isinstance(classes, (list, tuple)):
        for item in classes:
            if not isinstance(item, dict) or "value" not in item:
                return None, "classes as a list needs entries like {\"value\": 1, \"name\": \"Forest\"}."
            pairs.append((item["value"], item.get("name", "")))
    else:
        return None, "classes must be a mapping {value: name} or a list of {value, name}."
    out = {}
    for value, name in pairs:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None, f"class value '{value}' is not a number."
        if number != int(number):
            return None, f"class value '{value}' is not a whole number."
        out[int(number)] = str(name).strip()[:60]
    return out, None


def row_areas_ha(geotransform, rows, is_geographic, metres_per_unit=1.0):
    """List of the cell area in hectares for each raster row, or None when the CRS is neither projected nor geographic (`is_geographic` None).
    `geotransform` is GDAL's (x0, dx, 0, y0, 0, dy) with dy negative for a north-up raster. Pure."""
    _x0, dx, _r1, y0, _r2, dy = geotransform
    if is_geographic is None:
        return None
    if not is_geographic:
        area = abs(dx * metres_per_unit) * abs(dy * metres_per_unit) / M2_PER_HA
        return [area] * rows
    out = []
    dlon = math.radians(abs(dx))
    for i in range(rows):
        lat_a = y0 + i * dy
        lat_b = y0 + (i + 1) * dy
        band = abs(math.sin(math.radians(lat_a)) - math.sin(math.radians(lat_b)))
        out.append(AUTHALIC_RADIUS_M ** 2 * dlon * band / M2_PER_HA)
    return out


def cross_tab(a, b, valid, row_ha=None):
    """{'classes': [values], 'counts': 2-D int array, 'hectares': 2-D float array or None, 'valid_cells': n} for rasters `a` and `b` (2-D) over `valid` (2-D bool).
    Raises ValueError when a class value is not a whole number or there are more than MAX_CLASSES classes. `row_ha` is the cell area of each row. Pure numpy."""
    np = _np()
    a = np.asarray(a)
    b = np.asarray(b)
    keep = np.asarray(valid, dtype=bool) & np.isfinite(a) & np.isfinite(b)
    av, bv = a[keep], b[keep]
    if av.size and (np.any(av != np.round(av)) or np.any(bv != np.round(bv))):
        raise ValueError("the rasters hold non-whole values, so they are not class rasters; reclassify them first.")
    classes = sorted(set(np.unique(av.astype(np.int64)).tolist()) | set(np.unique(bv.astype(np.int64)).tolist()))
    if len(classes) > MAX_CLASSES:
        raise ValueError(f"{len(classes)} distinct values is more than the {MAX_CLASSES} classes a change matrix handles; these look continuous, reclassify them first.")
    k = len(classes)
    if k == 0:
        return {"classes": [], "counts": np.zeros((0, 0), dtype=np.int64), "hectares": None, "valid_cells": 0}
    index = {value: i for i, value in enumerate(classes)}
    lookup = np.vectorize(index.__getitem__, otypes=[np.int64])
    ia, ib = lookup(av.astype(np.int64)), lookup(bv.astype(np.int64))
    flat = ia * k + ib
    counts = np.bincount(flat, minlength=k * k).reshape(k, k).astype(np.int64)
    hectares = None
    if row_ha is not None:
        rows_idx = np.nonzero(keep)[0]
        weights = np.asarray(row_ha, dtype=np.float64)[rows_idx]
        hectares = np.bincount(flat, weights=weights, minlength=k * k).reshape(k, k)
    return {"classes": classes, "counts": counts, "hectares": hectares, "valid_cells": int(keep.sum())}


def summarise(tab, names=None):
    """(per_class rows, transitions rows, totals) from a cross_tab result. per_class: value, name, cells_before, cells_after, persistence, loss, gain, net, and the
    same in hectares and percent of the valid cells when hectares are known. transitions: every non-empty from-to pair. Pure."""
    names = names or {}
    classes, counts, area = tab["classes"], tab["counts"], tab["hectares"]
    total = int(tab["valid_cells"])
    total_ha = float(area.sum()) if area is not None else None

    def pct(cells):
        return round(100.0 * cells / total, 4) if total else 0.0
    per_class = []
    for i, value in enumerate(classes):
        before, after, stay = int(counts[i].sum()), int(counts[:, i].sum()), int(counts[i, i])
        row = {"value": value, "name": names.get(value, ""), "cells_before": before, "cells_after": after, "persistence": stay,
               "loss": before - stay, "gain": after - stay, "net": after - before, "percent_before": pct(before), "percent_after": pct(after)}
        if area is not None:
            row.update({"ha_before": round(float(area[i].sum()), 4), "ha_after": round(float(area[:, i].sum()), 4),
                        "ha_persistence": round(float(area[i, i]), 4), "ha_loss": round(float(area[i].sum() - area[i, i]), 4),
                        "ha_gain": round(float(area[:, i].sum() - area[i, i]), 4), "ha_net": round(float(area[:, i].sum() - area[i].sum()), 4)})
        per_class.append(row)
    transitions = []
    for i, src in enumerate(classes):
        for j, dst in enumerate(classes):
            cells = int(counts[i, j])
            if cells:
                row = {"from": src, "from_name": names.get(src, ""), "to": dst, "to_name": names.get(dst, ""), "cells": cells, "percent": pct(cells)}
                if area is not None:
                    row["hectares"] = round(float(area[i, j]), 4)
                transitions.append(row)
    changed = total - int(sum(counts[i, i] for i in range(len(classes))))
    totals = {"valid_cells": total, "changed_cells": changed, "percent_changed": pct(changed)}
    if total_ha is not None:
        totals["hectares"] = round(total_ha, 4)
        totals["changed_hectares"] = round(total_ha - float(sum(area[i, i] for i in range(len(classes)))), 4)
    return per_class, transitions, totals
