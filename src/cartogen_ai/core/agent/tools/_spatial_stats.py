"""Spatial autocorrelation statistics (PLAN-023 R2-1), pure Python, no QGIS, no numpy: global Moran's I (Moran 1950) and Local Moran's I / LISA (Anselin 1995), each with a permutation test.

Why permutation: the textbook normal-approximation formulas assume the values are normal or randomly drawn from a normal population; shuffling the observed values over the map and recomputing the statistic needs no such
assumption and makes the p-value mean what it says (how often a random arrangement of THESE values looks this clustered). It costs `permutations` x (links) operations, which the caller must cap.

Reproducibility: the shuffles are driven by random.Random(seed).random() through our own Fisher-Yates, not random.shuffle / random.sample, whose algorithms have changed between Python releases; the same seed gives the same
numbers on Python 3.10 and 3.11 and on Windows and Linux.

Definitions (z = value minus mean, n features, w the weights from _spatial_weights.standardise):
  I      = (n / S0) * sum_i z_i * lag_i / sum_i z_i^2,  lag_i = sum_j w_ij z_j,  S0 = sum of all weights.  E[I] = -1 / (n - 1) under no autocorrelation.
  I_i    = (z_i / m2) * lag_i with m2 = sum z^2 / n (Local Moran). The permutation for I_i holds z_i fixed and draws the neighbour values from the other n - 1 values (conditional permutation).
Pseudo p-values use (extreme count + 1) / (permutations + 1); two-sided p = min(1, 2 x the smaller one-sided p).
Local p-values are NOT corrected for the many tests (one per feature); the caller says so. A statistic is evidence of a pattern, not of its cause."""
import math
import random

from . import _spatial_weights as sw

MIN_PERMUTATIONS = 99
MAX_PERMUTATIONS = 9999
MAX_WORK = 25_000_000          # links x permutations: a few seconds in plain Python on the QGIS main thread
LOCAL_CLASSES = ("HH", "LL", "HL", "LH", "not significant", "no neighbours")


class SeededShuffler:
    """Fisher-Yates driven by random.Random(seed).random(), identical on every Python 3.x."""

    def __init__(self, seed):
        self._rng = random.Random(seed)  # noqa: S311 -- a reproducible statistical simulation, not security

    def below(self, n):
        return min(int(self._rng.random() * n), n - 1)

    def shuffle(self, items):
        for i in range(len(items) - 1, 0, -1):
            j = self.below(i + 1)
            items[i], items[j] = items[j], items[i]
        return items


def check_work(neighbours, permutations):
    """None when the request is affordable, else the reason it is not."""
    if isinstance(permutations, bool) or not isinstance(permutations, int) or not MIN_PERMUTATIONS <= permutations <= MAX_PERMUTATIONS:
        return f"permutations must be a whole number from {MIN_PERMUTATIONS} to {MAX_PERMUTATIONS}."
    work = sw.link_count(neighbours) * permutations
    if work > MAX_WORK:
        return (f"{sw.link_count(neighbours):,} neighbour links x {permutations} permutations is {work:,} steps, above the {MAX_WORK:,} this tool will run in one go. "
                "Use fewer permutations (99 is the minimum), fewer neighbours, or a smaller layer.")
    return None


def _clean(values):
    out = []
    for v in values:
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or math.isinf(v):
            raise ValueError("every value must be a finite number (no empty cells or text)")
        out.append(float(v))
    if len(out) < 3:
        raise ValueError("at least 3 features are needed")
    return out


def _p_values(observed, simulated):
    n = len(simulated)
    greater = (sum(1 for s in simulated if s >= observed) + 1) / (n + 1)
    less = (sum(1 for s in simulated if s <= observed) + 1) / (n + 1)
    return greater, less, min(1.0, 2 * min(greater, less))


def _lag_sum(weights, z):
    return sum(z[i] * sum(w * z[j] for j, w in row) for i, row in enumerate(weights))


def morans_i(values, neighbours, style="row", permutations=999, seed=1):
    """Global Moran's I with a permutation test. Returns {'n', 'I', 'expected_I', 'z_sim', 'p_greater', 'p_less', 'p_value', 'permutations', 'seed', 'style', 'S0', 'islands'}.
    ValueError (with the cause in words) for non-numeric values, fewer than 3 features, a constant field, weights with no link at all, or an unaffordable request. `neighbours[i]` lists the other
    features i counts as near (see _spatial_weights)."""
    x = _clean(values)
    n = len(x)
    if len(neighbours) != n:
        raise ValueError("the weights and the values have different lengths")
    problem = check_work(neighbours, permutations)
    if problem:
        raise ValueError(problem)
    mean = sum(x) / n
    z = [v - mean for v in x]
    m2 = sum(v * v for v in z)
    if m2 == 0:
        raise ValueError("all values are equal, so Moran's I is undefined (there is no variation to be clustered)")
    weights = sw.standardise(neighbours, style)
    s0 = sum(w for row in weights for _j, w in row)
    if s0 == 0:
        raise ValueError("no feature has a neighbour, so there is nothing to compare")
    observed = (n / s0) * _lag_sum(weights, z) / m2
    shuffler = SeededShuffler(seed)
    work = list(z)
    simulated = []
    for _ in range(permutations):
        shuffler.shuffle(work)
        simulated.append((n / s0) * _lag_sum(weights, work) / m2)
    mean_sim = sum(simulated) / permutations
    sd_sim = math.sqrt(sum((s - mean_sim) ** 2 for s in simulated) / (permutations - 1))
    greater, less, two = _p_values(observed, simulated)
    return {"n": n, "I": observed, "expected_I": -1.0 / (n - 1), "z_sim": (observed - mean_sim) / sd_sim if sd_sim > 0 else None,
            "p_greater": greater, "p_less": less, "p_value": two, "permutations": permutations, "seed": seed, "style": style, "S0": s0, "islands": sw.islands(neighbours)}


def quadrant(z, lag):
    """'HH', 'LL', 'HL' or 'LH' from the signs of a feature's deviation and its neighbours' mean deviation; None when either is zero."""
    if z == 0 or lag == 0:
        return None
    return ("H" if z > 0 else "L") + ("H" if lag > 0 else "L")


def local_morans(values, neighbours, style="row", permutations=999, seed=1, alpha=0.05):
    """Local Moran's I per feature with a conditional permutation test. Returns {'features': [{'local_i', 'lag', 'z', 'p_value', 'class'}], 'counts': {class: n}, 'alpha', 'permutations', 'seed', 'note'}.
    A feature with no neighbour gets class 'no neighbours' and no statistic. class is the quadrant (HH high among high, LL low among low, HL a high outlier among low, LH a low outlier among high) when p <= alpha, else
    'not significant'. The p-values are not corrected for testing every feature."""
    x = _clean(values)
    n = len(x)
    if len(neighbours) != n:
        raise ValueError("the weights and the values have different lengths")
    if isinstance(alpha, bool) or not isinstance(alpha, (int, float)) or not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    problem = check_work(neighbours, permutations)
    if problem:
        raise ValueError(problem)
    mean = sum(x) / n
    z = [v - mean for v in x]
    m2 = sum(v * v for v in z) / n
    if m2 == 0:
        raise ValueError("all values are equal, so Local Moran's I is undefined (there is no variation to be clustered)")
    weights = sw.standardise(neighbours, style)
    if all(not row for row in weights):
        raise ValueError("no feature has a neighbour, so there is nothing to compare")
    shuffler = SeededShuffler(seed)
    features, counts = [], dict.fromkeys(LOCAL_CLASSES, 0)
    for i, row in enumerate(weights):
        if not row:
            features.append({"local_i": None, "lag": None, "z": z[i], "p_value": None, "class": "no neighbours"})
            counts["no neighbours"] += 1
            continue
        k, w = len(row), row[0][1]
        lag = sum(wj * z[j] for j, wj in row)
        observed = z[i] / m2 * lag
        others = [j for j in range(n) if j != i]
        simulated = []
        for _ in range(permutations):
            for pos in range(k):                                    # partial Fisher-Yates: the first k places become a uniform random k-subset
                swap = pos + shuffler.below(len(others) - pos)
                others[pos], others[swap] = others[swap], others[pos]
            simulated.append(z[i] / m2 * w * sum(z[j] for j in others[:k]))
        _g, _l, p = _p_values(observed, simulated)
        q = quadrant(z[i], lag)
        label = q if (q is not None and p <= alpha) else "not significant"
        counts[label] += 1
        features.append({"local_i": observed, "lag": lag, "z": z[i], "p_value": p, "class": label})
    return {"features": features, "counts": counts, "alpha": alpha, "permutations": permutations, "seed": seed,
            "note": "p-values are per feature and not corrected for testing every feature; treat a few isolated 'significant' features with caution"}


def interpret_global(result, alpha=0.05):
    """One plain sentence for a morans_i result: what the number says and how sure the permutation test is. It says nothing about WHY a pattern exists."""
    i, expected, p = result["I"], result["expected_I"], result["p_value"]
    figures = f"Moran's I = {i:.3f} (what chance alone would give is about {expected:.3f}; permutation p = {p:.3f} from {result['permutations']} shuffles)"
    if p > alpha:
        return f"{figures}. This map is not distinguishable from a random arrangement of the same values: no clear spatial pattern at the {alpha:.2f} level."
    if i > expected:
        return f"{figures}. Neighbouring features tend to have SIMILAR values: high values sit near high values and low near low, more than chance explains."
    return f"{figures}. Neighbouring features tend to have DIFFERENT values: high values sit near low values, more than chance explains."


# --------------------------------------------------------------------------------------------------------------------------------------------------------------------
# Getis-Ord Gi* (PLAN-023 R2-2)
# --------------------------------------------------------------------------------------------------------------------------------------------------------------------
HOT_COLD_LEVELS = ((0.01, 99), (0.05, 95), (0.10, 90))


def normal_two_sided_p(z):
    """Two-sided p-value of a standard-normal z: 2 x (1 - Phi(|z|))."""
    return math.erfc(abs(z) / math.sqrt(2))


def gi_star(values, neighbours):
    """Getis-Ord Gi* z-score (Ord and Getis 1995) for every feature, with binary weights that INCLUDE the feature itself:
        z_i = (sum_j w_ij x_j - Xbar x sum_j w_ij) / (S x sqrt((n x sum_j w_ij^2 - (sum_j w_ij)^2) / (n - 1))),   Xbar = mean, S = sqrt(sum x^2 / n - Xbar^2).
    Returns [{'z', 'p_value', 'neighbours'}] in feature order; p is the two-sided normal p of z (an approximation that is poor for strongly skewed values: say so). A feature with no neighbour at all gets z and p None
    (its window would be itself alone, which tests nothing). A field with no variation has z = 0 and p = 1 everywhere. ValueError for non-numeric values, fewer than 3 features, or a length mismatch."""
    x = _clean(values)
    n = len(x)
    if len(neighbours) != n:
        raise ValueError("the weights and the values have different lengths")
    mean = sum(x) / n
    s2 = sum(v * v for v in x) / n - mean * mean
    s = math.sqrt(s2) if s2 > 0 else 0.0
    out = []
    for i, row in enumerate(neighbours):
        if not row:
            out.append({"z": None, "p_value": None, "neighbours": 0})
            continue
        window = [i, *row]
        k = len(window)                                   # binary weights: sum w = sum w^2 = k
        if s == 0:
            out.append({"z": 0.0, "p_value": 1.0, "neighbours": len(row)})
            continue
        spread = n * k - k * k
        denominator = s * math.sqrt(spread / (n - 1)) if spread > 0 else 0.0
        z = (sum(x[j] for j in window) - mean * k) / denominator if denominator > 0 else 0.0
        out.append({"z": z, "p_value": normal_two_sided_p(z), "neighbours": len(row)})
    return out


def benjamini_hochberg(p_values):
    """Adjusted p-values (q-values) by the Benjamini-Hochberg step-up procedure (1995): reject the tests with q <= alpha to keep the expected share of false discoveries at or below alpha. Order is preserved.
    q_(i) = min over j >= i of p_(j) x m / j for the sorted p-values. ValueError for a value outside [0, 1]."""
    m = len(p_values)
    if any(isinstance(p, bool) or not isinstance(p, (int, float)) or not 0 <= p <= 1 for p in p_values):
        raise ValueError("every p-value must be a number from 0 to 1")
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [0.0] * m
    running = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        running = min(running, p_values[i] * m / rank)
        adjusted[i] = running
    return adjusted


def hot_cold_class(z, level_p, alpha=0.05):
    """'Hot spot 99%', 'Cold spot 95%' ... or 'Not significant' from the sign of z and the p-value used for the decision (raw or BH-adjusted). The confidence level is the strictest of 99, 95, 90 the p-value
    meets, and nothing weaker than `alpha` is reported (alpha 0.05 reports 99 and 95; 0.10 adds 90). A z of exactly 0 is never a spot."""
    if z is None or level_p is None or z == 0:
        return "Not significant"
    for cutoff, level in HOT_COLD_LEVELS:
        if level_p <= cutoff and cutoff <= alpha + 1e-12:
            return f"{'Hot' if z > 0 else 'Cold'} spot {level}%"
    return "Not significant"


def hotspots(values, neighbours, fdr=True, alpha=0.05):
    """Gi* z, p, the BH-adjusted p (when fdr) and the hot/cold class per feature. Returns {'features': [{'z', 'p_value', 'p_adjusted', 'class', 'neighbours'}], 'counts': {class: n}, 'fdr', 'alpha', 'tested'}.
    Features with no neighbour have class 'No neighbours' and take no part in the correction. ValueError for an alpha outside (0, 1)."""
    if isinstance(alpha, bool) or not isinstance(alpha, (int, float)) or not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    rows = gi_star(values, neighbours)
    tested = [i for i, r in enumerate(rows) if r["p_value"] is not None]
    adjusted = dict(zip(tested, benjamini_hochberg([rows[i]["p_value"] for i in tested]), strict=True)) if fdr else {}
    features, counts = [], {}
    for i, r in enumerate(rows):
        if r["p_value"] is None:
            label, q = "No neighbours", None
        else:
            q = adjusted.get(i, r["p_value"]) if fdr else None
            label = hot_cold_class(r["z"], q if fdr else r["p_value"], alpha)
        counts[label] = counts.get(label, 0) + 1
        features.append({"z": r["z"], "p_value": r["p_value"], "p_adjusted": q, "class": label, "neighbours": r["neighbours"]})
    return {"features": features, "counts": counts, "fdr": bool(fdr), "alpha": alpha, "tested": len(tested)}
