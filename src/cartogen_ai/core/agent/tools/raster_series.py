"""Per-pixel statistics over a time series of rasters (PLAN-023 R3-3): mean, linear trend per year, and z-score anomaly against a baseline.

Pure numpy and streaming: the rasters are added one at a time into running sums, so memory does not grow with the number of rasters (only a handful of
full-size float64 arrays are held). Every statistic is NoData, never 0, where there are too few valid observations in a cell.

Formulas (n valid observations in the cell, y the values, t the times in years):
  mean   = sum(y) / n
  trend  = (n sum(t y) - sum(t) sum(y)) / (n sum(t^2) - sum(t)^2)       ordinary least squares slope, in value units per year
  anomaly z = (value - mean_baseline) / sd_baseline                     sd is the SAMPLE sd (n - 1) of the baseline observations
Known answers (the tests): values 1, 2, 3, 4 at t = 0, 1, 2, 3 give slope 1.0 exactly; a baseline of 8, 10, 12 (mean 10, sd 2) and a value of 14 give z = 2.0.

Limits, stated: the trend is a straight-line fit, not a seasonal model, and a slope from a few observations is weak evidence (the default asks for at least
3); the tool reports the slope, not its significance. Times are decimal years; a date is converted as year + (day of year - 1) / days in that year."""
import datetime

MIN_OBSERVATIONS_TREND = 3
MIN_OBSERVATIONS_BASELINE = 3
STATISTICS = ("mean", "trend", "anomaly")


def _np():
    import numpy as np
    return np


def parse_time(value):
    """Decimal year from a number (taken as years already) or a string 'YYYY', 'YYYY-MM', 'YYYY-MM-DD' or an ISO date-time (the date part is used).
    Returns None for anything else. Pure."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value == value and abs(value) != float("inf") else None
    text = str(value or "").strip()
    if not text:
        return None
    parts = text[:10].split("-")
    try:
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 and parts[1] else 1
        day = int(parts[2]) if len(parts) > 2 and parts[2] else 1
        when = datetime.date(year, month, day)
    except (ValueError, IndexError):
        try:
            number = float(text)
        except ValueError:
            return None
        return number if number == number and abs(number) != float("inf") else None
    days = 366 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 365
    return year + (when.timetuple().tm_yday - 1) / days


def parse_times(values):
    """([decimal years], error text or None) for a list of times. The error names the first value that is not a time. Pure."""
    out = []
    for value in values or []:
        parsed = parse_time(value)
        if parsed is None:
            return None, f"'{value}' is not a time: use a year such as 2021, a date such as 2021-06-15, or a number of years."
        out.append(parsed)
    return out, None


class SeriesAccumulator:
    """Running sums for one statistic over rasters added one at a time. `kind` is 'mean', 'trend' or 'baseline' (the baseline of an anomaly)."""

    def __init__(self, shape, kind):
        np = _np()
        if kind not in ("mean", "trend", "baseline"):
            raise ValueError(f"unknown accumulator kind '{kind}'")
        self.kind = kind
        self.n = np.zeros(shape, dtype=np.float64)
        self.sy = np.zeros(shape, dtype=np.float64)
        self.syy = np.zeros(shape, dtype=np.float64) if kind == "baseline" else None
        if kind == "trend":
            self.st = np.zeros(shape, dtype=np.float64)
            self.stt = np.zeros(shape, dtype=np.float64)
            self.sty = np.zeros(shape, dtype=np.float64)

    def add(self, values, valid, t=0.0):
        """Adds one raster: `values` (2-D), `valid` (2-D bool, False where NoData or not finite), `t` its time in years (trend only)."""
        np = _np()
        valid = np.asarray(valid, dtype=bool) & np.isfinite(values)
        y = np.where(valid, values, 0.0).astype(np.float64)
        w = valid.astype(np.float64)
        self.n += w
        self.sy += y
        if self.kind == "baseline":
            self.syy += y * y
        elif self.kind == "trend":
            self.st += w * t
            self.stt += w * t * t
            self.sty += y * t

    def mean(self, min_obs=1):
        """(mean float32, defined mask): NoData where fewer than `min_obs` valid observations."""
        np = _np()
        ok = self.n >= max(1, int(min_obs))
        out = np.zeros(self.n.shape, dtype=np.float64)
        np.divide(self.sy, self.n, out=out, where=ok)
        return out.astype(np.float32), ok

    def trend(self, min_obs=MIN_OBSERVATIONS_TREND):
        """(slope per year float32, defined mask): NoData where fewer than `min_obs` observations, or all observations share one time."""
        np = _np()
        den = self.n * self.stt - self.st * self.st
        ok = (self.n >= max(2, int(min_obs))) & (np.abs(den) > 1e-12)
        out = np.zeros(self.n.shape, dtype=np.float64)
        np.divide(self.n * self.sty - self.st * self.sy, den, out=out, where=ok)
        return out.astype(np.float32), ok

    def anomaly(self, values, valid, min_obs=MIN_OBSERVATIONS_BASELINE):
        """(z float32, defined mask) of `values` against this baseline: NoData where the value is NoData, the baseline has fewer than `min_obs`
        observations, or the baseline has no spread (sd 0)."""
        np = _np()
        valid = np.asarray(valid, dtype=bool) & np.isfinite(values)
        enough = self.n >= max(2, int(min_obs))
        n = np.where(enough, self.n, 1.0)
        mean = self.sy / n
        var = np.maximum((self.syy - self.sy * self.sy / n) / np.maximum(n - 1.0, 1.0), 0.0)
        sd = np.sqrt(var)
        ok = valid & enough & (sd > 0)
        out = np.zeros(self.n.shape, dtype=np.float64)
        np.divide(np.where(valid, values, 0.0) - mean, sd, out=out, where=ok)
        return out.astype(np.float32), ok


def check_request(statistic, names, times=None, target=None, baseline=None, min_observations=None):
    """Error text for a request that cannot be run, else None. `names` are the raster layer references in order. Pure."""
    stat = str(statistic or "").strip().lower()
    if stat not in STATISTICS:
        return f"statistic must be one of {', '.join(STATISTICS)}."
    if not names:
        return "rasters needs a list of raster layer names."
    if min_observations is not None:
        try:
            if int(min_observations) < 1:
                return "min_observations must be 1 or more."
        except (TypeError, ValueError):
            return "min_observations must be a whole number."
    if stat == "trend":
        if not times or len(times) != len(names):
            return f"trend needs one time per raster ({len(names)} rasters, {len(times or [])} times)."
        if len(names) < 3:
            return "trend needs at least 3 rasters: a line through two points says nothing about a trend."
        if len(set(times)) < 2:
            return "trend needs rasters from at least two different times."
    if stat == "anomaly":
        pool = [n for n in names if n != target] if target else list(names[:-1])
        chosen = baseline if baseline else pool
        if target and target not in names:
            return f"target '{target}' is not one of the rasters."
        if len(chosen) < 3:
            return "anomaly needs at least 3 baseline rasters to estimate a mean and a spread."
        if target and target in chosen:
            return "the target raster cannot also be part of its own baseline."
    return None
