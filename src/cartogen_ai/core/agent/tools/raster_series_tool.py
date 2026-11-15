"""raster_time_series_stats (PLAN-023 R3-3): per-pixel mean, trend per year and anomaly over rasters in the project.

The statistics are computed by the pure, streaming code in raster_series.py (hand-checked offline): the rasters are read one at a time and added into
running sums, so memory does not grow with the number of rasters. The result is a Float32 GeoTIFF with an explicit NoData value, added to the project.
Cells with too few valid observations are NoData, never 0.

`rasters` is an ordered list of raster layer names (or 'layer name@band'); for a trend `times` gives each one's time (a year, a date, or a number of years);
for an anomaly the `target` raster (default: the last one) is compared with the `baseline` rasters (default: all the others). The rasters must share one
pixel grid (the existing check, with the same align_to_first option). Items found by a STAC search (R3-2) are not accepted yet: load them first.

Written without a QGIS install; tests/test_raster_series_tool_live.py is its first execution in CI."""
import contextlib
import os

from . import raster_indices as ri
from . import raster_numpy as rn
from . import raster_series as rs
from .raster_tools import _ALIGN_PARAMS, _find_layer_by_name, _grid_or_error, _with_alignment_note
from .registry import register_tool
from .spectral_index_tool import NODATA, write_float_raster

try:
    from qgis.core import QgsProject, QgsRasterLayer
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

MAX_RASTERS = 60
ACCUMULATOR_ARRAYS = 8        # full-size float64 arrays held at once (the largest statistic holds five), counted against the existing value budget


@register_tool(
    "raster_time_series_stats",
    "Per-pixel statistics over a time series of rasters already in the project: 'mean' (average of the valid values), 'trend' (straight-line slope in value "
    "units per YEAR, for example NDVI change per year; needs `times`, one per raster, and at least 3 rasters) or 'anomaly' (z-score of one raster against "
    "the mean and standard deviation of the baseline rasters: how unusual is this month compared with the other years). `rasters` is an ordered list of "
    "layer names (or 'layer name@band'). For a trend give `times` as years, dates ('2021-06-15') or numbers of years. For an anomaly the `target` raster "
    "(default: the last) is compared with the `baseline` rasters (default: all the others, at least 3). Cells with too few valid observations are NoData. "
    "The rasters must share one pixel grid (or pass align_to_first). It reports the slope, not its statistical significance. Adds a new raster layer.",
    {"type": "object", "properties": {
        "rasters": {"type": "array", "items": {"type": "string"}, "description": "Raster layer names in time order (max 60)."},
        "statistic": {"type": "string", "enum": list(rs.STATISTICS), "description": "mean, trend or anomaly (default mean)."},
        "times": {"type": "array", "items": {"type": ["string", "number"]},
                  "description": "Trend only: the time of each raster, in the same order: a year, a date such as 2021-06-15, or a number of years."},
        "target": {"type": "string", "description": "Anomaly only: the raster to score (default: the last one in `rasters`)."},
        "baseline": {"type": "array", "items": {"type": "string"}, "description": "Anomaly only: the baseline rasters (default: all the others)."},
        "min_observations": {"type": "integer", "description": "Fewest valid values a cell needs (defaults: 1 for mean, 3 for trend and for the baseline)."},
        "output_name": {"type": "string", "description": "Name of the new layer (default ts_mean, ts_trend or ts_anomaly)."},
        **_ALIGN_PARAMS},
     "required": ["rasters"]},
    keywords=[
        "time series", "trend per year", "change per year", "anomaly", "z-score", "compared with the baseline", "long term mean", "vegetation trend",
        "greening", "browning", "decline over the years", "unusually dry", "departure from normal",
    ],
)
def raster_time_series_stats(rasters, statistic="mean", times=None, target=None, baseline=None, min_observations=None, output_name=None,
                             align_to_first=False, resampling="bilinear"):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    stat = str(statistic or "mean").strip().lower()
    refs = [str(r) for r in (rasters or [])]
    if len(refs) > MAX_RASTERS:
        return {"error": f"{len(refs)} rasters is more than the {MAX_RASTERS} limit; use fewer or pre-combine them."}
    years = None
    if stat == "trend":
        years, time_error = rs.parse_times(times)
        if time_error:
            return {"error": time_error}
    problem = rs.check_request(stat, refs, years, target, baseline, min_observations)
    if problem:
        return {"error": problem}
    base_refs = list(baseline) if baseline else None
    if stat == "anomaly":
        target = target or refs[-1]
        base_refs = base_refs or [r for r in refs if r != target]
        ordered = [*base_refs, target]                                 # the baseline first, the target last
    else:
        ordered = refs
    layers = []
    for ref in ordered:
        layer_name, band_no = ri.parse_band_ref(ref)
        if layer_name is None:
            return {"error": f"'{ref}' is not a valid raster reference: use a layer name or 'layer name@band' with band 1 or higher."}
        layer = _find_layer_by_name(layer_name)
        if layer is None:
            return {"error": f"Layer '{layer_name}' not found."}
        if not isinstance(layer, QgsRasterLayer):
            return {"error": f"'{layer_name}' is not a raster layer."}
        if band_no > layer.bandCount():
            return {"error": f"'{layer_name}' has {layer.bandCount()} band(s); band {band_no} was asked for."}
        layers.append((layer, band_no))
    unique = list({layer.id(): layer for layer, _b in layers}.values())
    used, grid_error, align_note = _grid_or_error(unique, align_to_first, resampling)
    if grid_error:
        return {"error": grid_error}
    by_id = {orig.id(): new for orig, new in zip(unique, used, strict=True)}
    first = by_id[unique[0].id()]
    try:
        rn.check_memory_budget(first.width(), first.height(), ACCUMULATOR_ARRAYS)
        shape = (first.height(), first.width())
        info = None
        n_used = len(layers)
        min_obs = None if min_observations is None else int(min_observations)

        def read(layer_band):
            nonlocal info
            layer, band_no = layer_band
            data, valid, band_info = rn.read_bands(by_id[layer.id()].source(), [band_no])
            info = info or band_info
            return data[:, :, 0], valid

        if stat == "mean":
            acc = rs.SeriesAccumulator(shape, "mean")
            for item in layers:
                values, valid = read(item)
                acc.add(values, valid)
            out, ok = acc.mean(min_obs or 1)
        elif stat == "trend":
            t0 = min(years)
            acc = rs.SeriesAccumulator(shape, "trend")
            for item, year in zip(layers, years, strict=True):
                values, valid = read(item)
                acc.add(values, valid, year - t0)
            out, ok = acc.trend(min_obs or rs.MIN_OBSERVATIONS_TREND)
        else:
            acc = rs.SeriesAccumulator(shape, "baseline")
            for item in layers[:-1]:
                values, valid = read(item)
                acc.add(values, valid)
            values, valid = read(layers[-1])
            out, ok = acc.anomaly(values, valid, min_obs or rs.MIN_OBSERVATIONS_BASELINE)
        path = write_float_raster(out, ok, info)
    except ValueError as e:
        return {"error": f"{stat}: {e}"}
    except Exception as e:
        return {"error": f"The {stat} could not be computed: {e}"}
    default_name = {"mean": "ts_mean", "trend": "ts_trend", "anomaly": "ts_anomaly"}[stat]
    out_name = (output_name or "").strip() or default_name
    layer_out = QgsRasterLayer(path, out_name)
    if not layer_out.isValid():
        with contextlib.suppress(OSError):
            os.remove(path)
        return {"error": f"The {stat} raster was written but could not be loaded: {path}"}
    QgsProject.instance().addMapLayer(layer_out)
    valid_cells = int(ok.sum())
    result = {
        "success": True, "layer_name": out_name, "statistic": stat, "rasters_used": n_used,
        "valid_cells": valid_cells, "no_data_cells": int(ok.size - valid_cells), "nodata_value": NODATA,
        "units": {"mean": "the input's units", "trend": "input units per year", "anomaly": "standard deviations from the baseline mean"}[stat],
        "limits": "A straight-line fit or a mean and spread, not a seasonal model; no significance test. NoData where a cell has too few valid values. "
                  "The rasters were read one at a time, but the result and its running sums are held in memory (clip a very large raster first).",
    }
    if stat == "trend":
        result["times_years"] = [round(y, 4) for y in years]
    if stat == "anomaly":
        result["target"] = target
        result["baseline"] = list(base_refs)
    if valid_cells:
        result["value_range"] = [round(float(out[ok].min()), 4), round(float(out[ok].max()), 4)]
    return _with_alignment_note(result, align_note)
