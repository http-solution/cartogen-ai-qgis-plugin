"""Management zones from one or more index rasters (PLAN-023 R3-5): seeded k-means, optional smoothing, merging of small zones, per-zone statistics.

Pure numpy, no QGIS and no GDAL: the known answers are checked offline.

Method, in order:
  1. every band is standardised (zero mean, unit standard deviation over the valid cells; a band with no spread becomes 0), so an index in 0..1 and one in -1..1 weigh equally;
  2. the existing seeded k-means of raster_numpy clusters the valid cells; zones are numbered 1..k by their mean of the FIRST band, lowest first, so zone 1 is always the lowest
     and a sequential colour ramp reads in order;
  3. optionally a 3 x 3 majority filter removes isolated cells (ties keep the cell's own zone);
  4. every connected patch (4-neighbour) of one zone whose area is below `min_zone_area_ha` is merged into the neighbouring zone whose mean is nearest to the patch's own mean
     (in the standardised space), smallest patches first, repeated until none is left or nothing can change;
  5. statistics per zone in the bands' own units.
Known answers (the tests): two flat patches of 0.2 and 0.8 with 2 zones give two zones whose means are exactly 0.2 and 0.8; one stray cell of 0.8 inside the 0.2 patch, with a
minimum area of two cells, is merged into the 0.2 zone.

What this is not: the zones describe differences in the index values only. They are not a yield forecast and not an input-rate recommendation, and nothing here says what to do on any zone."""
from . import raster_numpy as rn

MIN_ZONES = 2
MAX_ZONES = 8
MAX_BANDS = 5
MAX_CELLS = 4_000_000            # the connected-patch labelling holds several full-size integer arrays


def _np():
    import numpy as np
    return np


def standardise(values, valid):
    """(z array (rows, cols, bands) float64, means, sds) with each band standardised over the cells in `valid`. A band with no spread, or no valid cell, is all 0. Pure numpy."""
    np = _np()
    arr = np.asarray(values, dtype=np.float64)
    means, sds = [], []
    z = np.zeros_like(arr)
    for b in range(arr.shape[2]):
        band = arr[:, :, b]
        v = band[valid]
        mean = float(v.mean()) if v.size else 0.0
        sd = float(v.std()) if v.size else 0.0
        means.append(mean)
        sds.append(sd)
        if sd > 0:
            z[:, :, b] = np.where(valid, (band - mean) / sd, 0.0)
    return z, means, sds


def cluster(values, valid, k, seed=0):
    """(labels (rows, cols) int32, -1 where not valid, z) after standardising and clustering into k zones numbered 0..k-1 by their mean of the first band, lowest first.
    Raises ValueError for a bad k or fewer valid cells than zones."""
    np = _np()
    k = int(k)
    if not MIN_ZONES <= k <= MAX_ZONES:
        raise ValueError(f"n_zones must be between {MIN_ZONES} and {MAX_ZONES}.")
    valid = np.asarray(valid, dtype=bool)
    if int(valid.sum()) < k:
        raise ValueError(f"only {int(valid.sum())} valid cells: not enough for {k} zones.")
    z, _means, _sds = standardise(values, valid)
    raw, _centres = rn.kmeans(z[valid], k, seed=seed)
    first = np.asarray(values, dtype=np.float64)[:, :, 0][valid]
    order = sorted(range(k), key=lambda c: (float(first[raw == c].mean()) if np.any(raw == c) else float("inf"), c))
    remap = np.zeros(k, dtype=np.int32)
    for new, old in enumerate(order):
        remap[old] = new
    labels = np.full(valid.shape, -1, dtype=np.int32)
    labels[valid] = remap[raw]
    return labels, z


def majority_filter(labels):
    """One 3 x 3 majority pass over a label grid (-1 = not valid, left as it is). Each valid cell takes the most common zone in its 3 x 3 window (cells that are not valid do
    not vote); on a tie it keeps its own zone. Pure numpy."""
    np = _np()
    labels = np.asarray(labels)
    classes = [c for c in np.unique(labels).tolist() if c >= 0]
    if len(classes) < 2:
        return labels.copy()
    rows, cols = labels.shape
    padded = np.pad(labels, 1, constant_values=-1)
    counts = np.zeros((len(classes), rows, cols), dtype=np.int8)
    for i, c in enumerate(classes):
        for dr in (0, 1, 2):
            for dc in (0, 1, 2):
                counts[i] += (padded[dr:dr + rows, dc:dc + cols] == c)
    best = counts.argmax(axis=0)
    top = counts.max(axis=0)
    tie = (counts == top).sum(axis=0) > 1
    majority = np.array(classes, dtype=labels.dtype)[best]
    return np.where((labels >= 0) & ~tie, majority, labels)


def connected_components(labels):
    """(component id grid (-1 where not valid), number of components): 4-neighbour patches of equal label. Vectorised union-find with pointer jumping; pure numpy."""
    np = _np()
    labels = np.asarray(labels)
    rows, cols = labels.shape
    valid = labels >= 0
    idx = np.arange(rows * cols).reshape(rows, cols)
    same_h = (labels[:, :-1] == labels[:, 1:]) & valid[:, :-1] & valid[:, 1:]
    same_v = (labels[:-1, :] == labels[1:, :]) & valid[:-1, :] & valid[1:, :]
    u = np.concatenate([idx[:, :-1][same_h], idx[:-1, :][same_v]])
    v = np.concatenate([idx[:, 1:][same_h], idx[1:, :][same_v]])
    parent = np.arange(rows * cols)
    while u.size:
        pu, pv = parent[u], parent[v]
        low = np.minimum(pu, pv)
        if np.array_equal(pu, low) and np.array_equal(pv, low):
            break
        np.minimum.at(parent, pu, low)
        np.minimum.at(parent, pv, low)
        while True:
            jumped = parent[parent]
            if np.array_equal(jumped, parent):
                break
            parent = jumped
    comp = np.full(rows * cols, -1, dtype=np.int64)
    flat_valid = valid.ravel()
    roots, inverse = np.unique(parent[flat_valid], return_inverse=True)
    comp[flat_valid] = inverse
    return comp.reshape(rows, cols), len(roots)


def merge_small(labels, z, valid, row_ha, min_area_ha, max_passes=10):
    """(labels, merged patches): each connected patch smaller than `min_area_ha` takes the zone of the neighbouring patch whose zone mean is nearest to the patch's own mean in
    the standardised space `z`; smallest first; repeated up to `max_passes` times. `row_ha` is the cell area of each row. A patch with no neighbour stays. Pure numpy."""
    np = _np()
    labels = np.asarray(labels).copy()
    rows, cols = labels.shape
    if not min_area_ha or min_area_ha <= 0:
        return labels, 0
    weights = np.repeat(np.asarray(row_ha, dtype=np.float64), cols)
    z_flat = np.asarray(z).reshape(rows * cols, -1)
    merged_total = 0
    for _ in range(int(max_passes)):
        comp, n = connected_components(labels)
        flat = comp.ravel()
        inside = flat >= 0
        if n <= 1:
            break
        area = np.bincount(flat[inside], weights=weights[inside], minlength=n)
        small = [int(c) for c in np.argsort(area, kind="stable") if area[c] < min_area_ha]
        if not small:
            break
        order = np.argsort(flat, kind="stable")
        outside = int((~inside).sum())
        starts = np.concatenate([[0], np.cumsum(np.bincount(flat[inside], minlength=n))]) + outside
        zone_ids = [c for c in np.unique(labels).tolist() if c >= 0]
        zone_mean = {c: z_flat[(labels.ravel() == c)].mean(axis=0) for c in zone_ids}
        changed = 0
        for c in small:
            cells = order[starts[c]:starts[c + 1]]
            r, col = np.divmod(cells, cols)
            own = int(labels[r[0], col[0]])
            candidates = set()
            for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                rr, cc = r + dr, col + dc
                ok = (rr >= 0) & (rr < rows) & (cc >= 0) & (cc < cols)
                neighbour = labels[rr[ok], cc[ok]]
                candidates |= {int(x) for x in np.unique(neighbour) if x >= 0 and x != own}
            if not candidates:
                continue
            own_mean = z_flat[cells].mean(axis=0)
            best = min(sorted(candidates), key=lambda zone: float(((own_mean - zone_mean[zone]) ** 2).sum()))
            labels[r, col] = best
            changed += 1
        merged_total += changed
        if not changed:
            break
    return labels, merged_total


def zone_stats(labels, values, valid, row_ha):
    """List of {'zone' (1-based), 'cells', 'area_ha', 'percent', 'means' [one per band, original units]} for the zones present in `labels`, in zone order. Pure numpy."""
    np = _np()
    labels = np.asarray(labels)
    vals = np.asarray(values, dtype=np.float64)
    weights = np.repeat(np.asarray(row_ha, dtype=np.float64), labels.shape[1]).reshape(labels.shape)
    total = int((labels >= 0).sum())
    out = []
    for c in sorted(x for x in np.unique(labels).tolist() if x >= 0):
        mask = labels == c
        cells = int(mask.sum())
        out.append({"zone": c + 1, "cells": cells, "area_ha": float(weights[mask].sum()), "percent": round(100.0 * cells / total, 4) if total else 0.0,
                    "means": [float(vals[:, :, b][mask].mean()) for b in range(vals.shape[2])]})
    return out


def default_min_area_ha(total_area_ha):
    """The default minimum zone area: 1 percent of the valid area. Pure."""
    return 0.01 * float(total_area_ha)


def check_request(n_zones, n_bands, cells):
    """Error text for a request that cannot be run, else None. Pure."""
    try:
        k = int(n_zones)
    except (TypeError, ValueError):
        return "n_zones must be a whole number."
    if not MIN_ZONES <= k <= MAX_ZONES:
        return f"n_zones must be between {MIN_ZONES} and {MAX_ZONES} (3 to 5 is usual for management zones)."
    if not 1 <= n_bands <= MAX_BANDS:
        return f"give between 1 and {MAX_BANDS} rasters to cluster."
    if cells > MAX_CELLS:
        return f"the raster has {cells:,} cells, above the {MAX_CELLS:,} limit for zoning; clip it first."
    return None
