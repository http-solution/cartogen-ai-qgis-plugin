"""Watershed delineation from a DEM array: the GIS phase the hydrology tools said they did not have (showcase S1).

Why: engineering_tools.py computes Tc and the Rational Method discharge from numbers the caller supplies, but nothing measured the numbers.
The owner's live request ("determine watershed area, stream length, H, slope, return period 20 year, intensity, Tc and peak flow at this location")
was refused for lack of a basin (2026-10-04, by design: it must never be invented). This module measures them.

Method, the textbook D8 chain (O'Callaghan & Mark 1984; Barnes et al. 2014 for the depression filling):
  1. Priority-flood depression filling with a small epsilon so every cell has a strictly lower neighbour on a path to the edge.
  2. D8 flow direction: each cell drains to its steepest-descent neighbour (diagonals use the longer distance).
  3. Flow accumulation: cells counted from upstream, processed in descending filled elevation.
  4. The requested outlet is snapped to the highest-accumulation cell inside a snap distance (a coordinate read from a map is rarely on the
     DEM's derived channel); how far it moved is reported.
  5. The basin is everything that drains to the snapped outlet; its area is cell count x cell area.
  6. The longest hydraulic flow path is the upstream cell with the greatest flow distance to the outlet, followed downstream; H is the ORIGINAL
     (unfilled) DEM elevation there minus the outlet's, so filling does not change the reported drop.

Pure numpy and Python: no QGIS, so it is unit tested offline on synthetic terrain with known answers. Not a replacement for a hydrology package:
it is D8 on a ~30 m surface model, and the reply states the resolution, the snap distance and whether the basin touches the DEM edge (a
truncated basin). Cell sizes are taken as constant over the window (fine for a basin of a few tens of kilometres).
"""
import heapq
import math

_NEIGHBOURS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
EPSILON = 1e-3          # metres added per step while filling: enough to order cells, far below DEM vertical accuracy
DEFAULT_MIN_ACCUMULATION = 25   # cells: a snap target must drain at least this many cells to count as a channel


def _np():
    import numpy as np
    return np


def fill_depressions(dem, eps=EPSILON):
    """Priority-flood fill (Barnes et al. 2014) of a 2-D float array with no NaN: returns a copy in which every cell drains to the border."""
    np = _np()
    h, w = dem.shape
    z = dem.astype(np.float64).ravel().tolist()
    closed = bytearray(h * w)
    heap = []
    for r in range(h):
        for c in range(w):
            if r in (0, h - 1) or c in (0, w - 1):
                i = r * w + c
                closed[i] = 1
                heap.append((z[i], i))
    heapq.heapify(heap)
    while heap:
        level, i = heapq.heappop(heap)
        r, c = divmod(i, w)
        for dr, dc in _NEIGHBOURS:
            nr, nc = r + dr, c + dc
            if 0 <= nr < h and 0 <= nc < w:
                j = nr * w + nc
                if not closed[j]:
                    closed[j] = 1
                    if z[j] <= level:
                        z[j] = level + eps
                    heapq.heappush(heap, (z[j], j))
    return np.array(z, dtype=np.float64).reshape(h, w)


def flow_directions(filled, dx, dy):
    """Flat index of the cell each cell drains to (-1 for a cell with no lower neighbour: border outlets). Steepest descent over 8 neighbours."""
    np = _np()
    h, w = filled.shape
    best = np.zeros((h, w))
    target = np.full((h, w), -1, dtype=np.int64)
    padded = np.pad(filled, 1, mode="constant", constant_values=np.inf)      # +inf: nothing drains off the grid except by being an outlet
    rows, cols = np.indices((h, w))
    for dr, dc in _NEIGHBOURS:
        step = math.hypot(dc * dx, dr * dy)
        neighbour = padded[1 + dr:1 + dr + h, 1 + dc:1 + dc + w]
        slope = (filled - neighbour) / step
        better = slope > best
        best = np.where(better, slope, best)
        index = (rows + dr) * w + (cols + dc)
        target = np.where(better, index, target)
    return target.ravel()


def flow_accumulation(filled, down):
    """Number of cells draining through each cell (itself included), as a flat int array."""
    np = _np()
    order = np.argsort(-filled.ravel(), kind="stable").tolist()
    acc = [1] * down.size
    d = down.tolist()
    for i in order:
        t = d[i]
        if t >= 0:
            acc[t] += acc[i]
    return np.array(acc, dtype=np.int64)


def snap_to_channel(acc, row, col, radius_cells, min_accumulation=DEFAULT_MIN_ACCUMULATION):
    """(row, col, moved_cells, on_channel): the highest-accumulation cell within `radius_cells` of (row, col), ties broken toward the original point."""
    np = _np()
    h, w = acc.shape
    r0, r1 = max(0, row - radius_cells), min(h, row + radius_cells + 1)
    c0, c1 = max(0, col - radius_cells), min(w, col + radius_cells + 1)
    window = acc[r0:r1, c0:c1]
    rr, cc = np.indices(window.shape)
    dist = np.hypot(rr + r0 - row, cc + c0 - col)
    inside = dist <= radius_cells
    score = np.where(inside, window, -1).astype(np.float64) - dist * 1e-6
    k = int(np.argmax(score))
    r, c = int(rr.ravel()[k] + r0), int(cc.ravel()[k] + c0)
    return r, c, float(math.hypot(r - row, c - col)), bool(acc[r, c] >= min_accumulation)


def upstream_cells(down, outlet_index):
    """Flat indices of every cell that drains to `outlet_index` (itself included), in breadth-first order from the outlet."""
    np = _np()
    n = down.size
    has_target = down >= 0
    sources = np.nonzero(has_target)[0]
    order = np.argsort(down[has_target], kind="stable")
    sorted_sources = sources[order].tolist()
    sorted_targets = down[has_target][order]
    starts = np.searchsorted(sorted_targets, np.arange(n), side="left").tolist()
    ends = np.searchsorted(sorted_targets, np.arange(n), side="right").tolist()
    queue, seen = [outlet_index], {outlet_index}
    head = 0
    while head < len(queue):
        i = queue[head]
        head += 1
        for k in range(starts[i], ends[i]):
            j = sorted_sources[k]
            if j not in seen:
                seen.add(j)
                queue.append(j)
    return queue


def delineate(dem, dx_m, dy_m, row, col, snap_radius_m=300.0, min_accumulation=DEFAULT_MIN_ACCUMULATION):
    """Delineate the basin draining to the point (row, col) of `dem` (2-D array of metres, NaN = no data; cell sizes dx_m, dy_m in metres).

    Returns a dict (see the keys below) or {"error": ...}. Pure."""
    np = _np()
    dem = np.asarray(dem, dtype=np.float64)
    if dem.ndim != 2 or min(dem.shape) < 5:
        return {"error": "The DEM window is too small to delineate a basin."}
    h, w = dem.shape
    if not (0 <= row < h and 0 <= col < w):
        return {"error": "The outlet lies outside the DEM window."}
    if not (dx_m > 0 and dy_m > 0):
        return {"error": "The DEM cell size could not be determined."}
    nodata = ~np.isfinite(dem)
    if nodata.mean() > 0.2:
        return {"error": f"{nodata.mean() * 100:.0f}% of the DEM window has no data (sea or a gap); choose an inland outlet or another DEM."}
    low = float(np.nanmin(dem)) - 10.0
    work = np.where(nodata, low, dem)
    filled = fill_depressions(work)
    down = flow_directions(filled, dx_m, dy_m)
    acc2d = flow_accumulation(filled, down).reshape(h, w)
    radius = max(0, round(snap_radius_m / min(dx_m, dy_m)))
    orow, ocol, moved_cells, on_channel = snap_to_channel(acc2d, row, col, radius, min_accumulation)
    outlet = orow * w + ocol
    cells = upstream_cells(down, outlet)
    mask = np.zeros(h * w, dtype=bool)
    mask[cells] = True
    # flow distance to the outlet, along the D8 path, for every basin cell (BFS order: a cell's downstream neighbour is done first)
    dist = {outlet: 0.0}
    d = down.tolist()
    for i in cells[1:]:
        t = d[i]
        ri, ci = divmod(i, w)
        rt, ct = divmod(t, w)
        dist[i] = dist[t] + math.hypot((ci - ct) * dx_m, (ri - rt) * dy_m)
    far = max(cells, key=lambda i: dist[i])
    path, i = [], far
    while True:
        path.append(divmod(i, w))
        if i == outlet:
            break
        i = d[i]
    z_far, z_out = float(dem.ravel()[far]), float(dem.ravel()[outlet])
    mask2d = mask.reshape(h, w)
    touches_edge = bool(mask2d[0, :].any() or mask2d[-1, :].any() or mask2d[:, 0].any() or mask2d[:, -1].any())
    length = dist[far]
    drop = z_far - z_out
    return {
        "success": True,
        "mask": mask2d,
        "cells": len(cells),
        "area_km2": len(cells) * dx_m * dy_m / 1e6,
        "outlet_rc": (orow, ocol),
        "requested_rc": (row, col),
        "snap_moved_m": moved_cells * min(dx_m, dy_m),
        "snapped_to_channel": on_channel,
        "outlet_accumulation_cells": int(acc2d[orow, ocol]),
        "longest_flow_path_m": length,
        "path_rc": path,                         # upstream end first, outlet last
        "upstream_rc": divmod(far, w),
        "upstream_elevation_m": z_far,
        "outlet_elevation_m": z_out,
        "H_m": drop,
        "main_channel_slope_m_per_m": (drop / length) if length > 0 and drop > 0 else None,
        "max_basin_elevation_m": float(np.nanmax(np.where(mask2d, dem, -np.inf))),
        "mean_basin_elevation_m": float(np.nanmean(np.where(mask2d, dem, np.nan))),
        "touches_dem_edge": touches_edge,
    }


def mask_to_row_runs(mask):
    """[(row, first_col, last_col)] of the consecutive True cells in each row: a few hundred rectangles describe a basin, which is much
    faster to union into one polygon than one square per cell."""
    np = _np()
    runs = []
    for r in range(mask.shape[0]):
        cols = np.nonzero(mask[r])[0]
        if cols.size == 0:
            continue
        breaks = np.nonzero(np.diff(cols) > 1)[0]
        first = 0
        for b in [*breaks.tolist(), cols.size - 1]:
            runs.append((r, int(cols[first]), int(cols[b])))
            first = b + 1
    return runs


def cell_size_metres(geotransform, latitude, geographic):
    """(dx_m, dy_m) of one cell. A geographic grid (degrees) is converted at `latitude`; a projected one is taken to be in metres."""
    px, py = abs(geotransform[1]), abs(geotransform[5])
    if geographic:
        return px * 111320.0 * math.cos(math.radians(latitude)), py * 110574.0
    return px, py
