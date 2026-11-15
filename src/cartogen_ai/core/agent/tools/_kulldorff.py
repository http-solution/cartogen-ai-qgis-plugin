"""Kulldorff's circular spatial scan statistic, Poisson model (PLAN-023 R2-3): is there a group of nearby areas with MORE cases than their population explains, and how likely is a cluster this strong by chance alone?

Pure functions on plain lists plus numpy for the scan itself (the Monte Carlo repeats the scan hundreds of times, which is not practical in plain Python). numpy ships with QGIS; where it is missing `scan` raises
RuntimeError with the cause, and `llr`, `relative_risk` and `check_work` still work. Nothing here imports QGIS.

Method (Kulldorff 1997): every area is a point (its centroid) with a population and a case count. For every centre and every radius that includes whole 'rings' of nearer points, the circle holds c cases where
E = C x (population inside / total population) are expected under 'cases fall in proportion to population'. Only circles with c > E (more than expected) count, scored by the log likelihood ratio
LLR = c ln(c/E) + (C - c) ln((C - c)/(C - E)). The circle with the highest LLR is the most likely cluster. Its p-value comes from re-drawing all C cases at random in proportion to population (conditioned on C,
a multinomial), scanning again, and counting how often the best simulated LLR reaches the observed one: p = (1 + number reaching it) / (1 + replicates). Secondary clusters are the next best circles that share no area
with a stronger one, judged against the same simulated distribution."""
import importlib.util
import math

HAVE_NUMPY = importlib.util.find_spec("numpy") is not None


def _np():
    """numpy, imported on first use so this module loads (and the pure helpers work) where numpy is absent. A module-level `np = None` fallback fails mypy where numpy is installed (CI), so it is imported lazily instead."""
    import numpy as np
    return np

MIN_MONTE_CARLO = 99
MAX_MONTE_CARLO = 9999
MAX_AREAS = 1500
MAX_WORK = 400_000_000                   # areas^2 x replicates: about half a minute of numpy in the worst case
MIN_MAX_POP_FRACTION = 0.01
MAX_MAX_POP_FRACTION = 0.5               # Kulldorff's own recommendation: above 50% the 'cluster' is more than half the population, i.e. the rest is the signal


def llr(c, expected, total):
    """Poisson log likelihood ratio of a circle holding c of the `total` cases when `expected` were expected. 0 unless c > expected (the scan looks for EXCESS); handles c == total.
    Known answer: total 100, c 30, expected 15 -> 30 ln(30/15) + 70 ln(70/85) = 7.203."""
    if expected <= 0 or c <= expected:
        return 0.0
    out = c * math.log(c / expected)
    rest = total - c
    if rest > 0:
        out += rest * math.log(rest / (total - expected))
    return out


def relative_risk(c, expected, total):
    """Risk inside the circle relative to risk outside: (c / E) / ((C - c) / (C - E)). None when nothing is outside."""
    outside_cases, outside_expected = total - c, total - expected
    if outside_cases <= 0 or outside_expected <= 0 or expected <= 0:
        return None
    return (c / expected) / (outside_cases / outside_expected)


def check_work(areas, monte_carlo):
    """None when affordable, else the reason it is not."""
    if isinstance(monte_carlo, bool) or not isinstance(monte_carlo, int) or not MIN_MONTE_CARLO <= monte_carlo <= MAX_MONTE_CARLO:
        return f"monte_carlo must be a whole number from {MIN_MONTE_CARLO} to {MAX_MONTE_CARLO}."
    if areas > MAX_AREAS:
        return f"{areas:,} areas is above the {MAX_AREAS:,} this scan handles (it compares every area with every other). Aggregate to fewer, larger areas first."
    work = areas * areas * monte_carlo
    if work > MAX_WORK:
        most = max(MIN_MONTE_CARLO, MAX_WORK // (areas * areas))
        return (f"{areas:,} areas x {monte_carlo} replicates is above what this tool runs in one go. Use at most {most} replicates for this many areas"
                + (", or aggregate to fewer areas." if most < MIN_MONTE_CARLO + 1 else "."))
    return None


def _check_inputs(cases, populations, points, max_pop_fraction, max_radius):
    n = len(cases)
    if n < 3 or len(populations) != n or len(points) != n:
        raise ValueError("the scan needs at least 3 areas, each with a case count, a population and a location")
    for c in cases:
        if isinstance(c, bool) or not isinstance(c, (int, float)) or c != c or c < 0 or c != int(c):
            raise ValueError("case counts must be whole numbers, zero or more")
    for p in populations:
        if isinstance(p, bool) or not isinstance(p, (int, float)) or p != p or p <= 0:
            raise ValueError("every population must be a number above zero")
    if sum(cases) <= 0:
        raise ValueError("there are no cases at all, so there is nothing to find")
    if isinstance(max_pop_fraction, bool) or not isinstance(max_pop_fraction, (int, float)) or not MIN_MAX_POP_FRACTION <= max_pop_fraction <= MAX_MAX_POP_FRACTION:
        raise ValueError(f"max_pop_fraction must be between {MIN_MAX_POP_FRACTION} and {MAX_MAX_POP_FRACTION} (a cluster may hold at most half the population)")
    if max_radius is not None and (isinstance(max_radius, bool) or not isinstance(max_radius, (int, float)) or max_radius <= 0):
        raise ValueError("max_radius must be a distance above zero, or left out")


def _candidates(points, populations, max_pop_fraction, max_radius):
    """(order, cum_pop, valid, radius): for each centre i, `order[i]` lists all areas nearest first; prefix k (1-based) is a circle. valid[i, k-1] is True when the circle holds at most max_pop_fraction of the
    population, is within max_radius, and ends where the next area is strictly farther (a circle never splits areas at the same distance). radius[i, k-1] is the distance to the k-th area."""
    np = _np()
    xy = np.asarray(points, dtype=np.float64)
    pops = np.asarray(populations, dtype=np.float64)
    n = len(xy)
    d = np.sqrt(((xy[:, None, :] - xy[None, :, :]) ** 2).sum(axis=2))
    order = np.argsort(d, axis=1, kind="stable").astype(np.int32)
    radius = np.take_along_axis(d, order, axis=1)
    cum_pop = np.cumsum(pops[order], axis=1)
    valid = cum_pop <= max_pop_fraction * pops.sum() * (1 + 1e-12)
    if max_radius is not None:
        valid &= radius <= max_radius
    ends_ring = np.ones((n, n), dtype=bool)
    ends_ring[:, :-1] = radius[:, 1:] > radius[:, :-1]
    valid &= ends_ring
    return order, cum_pop, valid, radius


def scan(cases, populations, points, max_pop_fraction=0.5, max_radius=None, monte_carlo=999, seed=1, max_clusters=5, alpha=0.05):
    """Run the scan. Returns {'clusters': [{'centre', 'members', 'radius', 'cases', 'expected', 'relative_risk', 'llr', 'p_value'}], 'total_cases', 'total_population', 'monte_carlo', 'seed', 'alpha',
    'critical_llr', 'candidates'}. clusters[0] is the most likely cluster whether or not it is significant; later ones are only listed when p <= alpha and they share no area with a stronger one.
    `centre` and `members` are positions in the input lists. ValueError for bad input or when no circle satisfies the limits; RuntimeError when numpy is missing."""
    if not HAVE_NUMPY:
        raise RuntimeError("the cluster scan needs numpy, which ships with QGIS but was not found here")
    np = _np()
    _check_inputs(cases, populations, points, max_pop_fraction, max_radius)
    problem = check_work(len(cases), monte_carlo)
    if problem:
        raise ValueError(problem)
    if isinstance(max_clusters, bool) or not isinstance(max_clusters, int) or not 1 <= max_clusters <= 20:
        raise ValueError("max_clusters must be a whole number from 1 to 20")
    if isinstance(alpha, bool) or not isinstance(alpha, (int, float)) or not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    order, cum_pop, valid, radius = _candidates(points, populations, max_pop_fraction, max_radius)
    if not valid.any():
        raise ValueError("no circle satisfies the limits: one area alone may hold more than max_pop_fraction of the population, or max_radius is smaller than the distance to the nearest area. Relax a limit.")
    n = len(cases)
    case_array = np.asarray(cases, dtype=np.int64)
    pop_array = np.asarray(populations, dtype=np.float64)
    total = int(case_array.sum())
    total_pop = float(pop_array.sum())
    expected = total * cum_pop / total_pop
    expected_valid = expected[valid]
    rows, cols = np.nonzero(valid)

    def scores(case_vector):
        cum = np.cumsum(case_vector[order], axis=1)
        c = cum[rows, cols].astype(np.float64)
        e = expected_valid
        out = np.zeros_like(c)
        more = c > e
        cm, em = c[more], e[more]
        value = cm * np.log(cm / em)
        rest = total - cm
        tail = rest > 0
        value[tail] += rest[tail] * np.log(rest[tail] / (total - em[tail]))
        out[more] = value
        return out, cum

    observed, cum_observed = scores(case_array)
    rng = np.random.Generator(np.random.PCG64(int(seed)))
    probabilities = pop_array / total_pop
    simulated = np.empty(monte_carlo)
    for r in range(monte_carlo):
        simulated[r] = scores(rng.multinomial(total, probabilities).astype(np.int64))[0].max()
    critical = float(np.quantile(simulated, 1 - alpha))

    def p_of(value):
        return float((1 + int((simulated >= value).sum())) / (monte_carlo + 1))

    ranking = np.argsort(-observed, kind="stable")
    taken = np.zeros(n, dtype=bool)
    clusters = []
    for idx in ranking:
        value = float(observed[idx])
        if value <= 0:
            break
        if clusters and value < critical:
            break
        i, k = int(rows[idx]), int(cols[idx]) + 1
        members = order[i, :k]
        if taken[members].any():
            continue
        taken[members] = True
        c = int(cum_observed[i, k - 1])
        e = float(expected[i, k - 1])
        clusters.append({"centre": i, "members": [int(m) for m in members], "radius": float(radius[i, k - 1]), "cases": c, "expected": e, "relative_risk": relative_risk(c, e, total),
                         "llr": value, "p_value": p_of(value)})
        if len(clusters) >= max_clusters:
            break
    return {"clusters": clusters, "total_cases": total, "total_population": total_pop, "monte_carlo": monte_carlo, "seed": seed, "alpha": alpha, "critical_llr": critical,
            "candidates": int(valid.sum())}
