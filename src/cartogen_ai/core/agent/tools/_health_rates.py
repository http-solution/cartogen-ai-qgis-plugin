"""Rates, relative risk, standardised ratios and empirical-Bayes smoothing for areas (PLAN-023 R2-4). Pure Python, no QGIS, no numpy.

What this is: the plain arithmetic of small-area epidemiology on a count of cases and a population per area. What it is NOT: age or sex standardisation. The standardised ratio (SMR) uses expected counts the caller supplies, because the
right expected count needs the reference rates of the right strata and this tool never invents them.

Sources: crude rate and relative risk (any epidemiology text); Byar's approximation to the exact Poisson interval (Breslow and Day 1987, p. 69); global empirical-Bayes smoothing (Marshall 1991, 'Mapping disease and mortality
rates using empirical Bayes estimators', Applied Statistics 40: 283-294)."""
import math

Z95 = 1.959964
DEFAULT_PER = 100_000
DEFAULT_MIN_CASES = 5                    # the usual public-health rule: a count below 5 is unstable and, for small areas, can identify people
METHODS = ("crude", "smr", "eb")


def _whole(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and value == value and value >= 0 and value == int(value)


def _positive(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and value == value and value > 0 and value != math.inf


def check_inputs(cases, populations, expected=None, per=DEFAULT_PER, min_population=None, min_cases=DEFAULT_MIN_CASES):
    """ValueError naming the cause for anything the arithmetic cannot honestly use."""
    n = len(cases)
    if n < 2 or len(populations) != n:
        raise ValueError("rates need at least 2 areas, each with a case count and a population")
    bad = sum(1 for c in cases if not _whole(c))
    if bad:
        raise ValueError(f"{bad} case count(s) are not whole numbers of zero or more")
    bad = sum(1 for p in populations if not _positive(p))
    if bad:
        raise ValueError(f"{bad} population(s) are not above zero")
    if sum(cases) <= 0:
        raise ValueError("there are no cases at all, so no rate or risk can be compared")
    if not _positive(per):
        raise ValueError("per must be a number above zero, for example 100000")
    if expected is not None:
        if len(expected) != n:
            raise ValueError("expected counts must be given for every area")
        bad = sum(1 for e in expected if not _positive(e))
        if bad:
            raise ValueError(f"{bad} expected count(s) are not above zero; a standardised ratio needs an expected count in every area")
    if min_population is not None and not _positive(min_population):
        raise ValueError("min_population must be a number above zero, or left out")
    if isinstance(min_cases, bool) or not isinstance(min_cases, int) or min_cases < 0:
        raise ValueError("min_cases must be a whole number of zero or more")


def crude_rate(cases, population, per=DEFAULT_PER):
    return cases / population * per


def poisson_interval(count, z=Z95):
    """Byar's approximation to the exact Poisson confidence interval for a count: (lower, upper). Known answer: 10 cases -> 4.79 to 18.39 (exact: 4.795 to 18.390). A count of 0 has lower 0."""
    if count < 0:
        raise ValueError("a count cannot be negative")
    lower = 0.0 if count == 0 else count * (1 - 1 / (9 * count) - z / (3 * math.sqrt(count))) ** 3
    up = count + 1
    upper = up * (1 - 1 / (9 * up) + z / (3 * math.sqrt(up))) ** 3
    return max(lower, 0.0), upper


def smr(observed, expected):
    """Indirectly standardised ratio O / E with Byar's interval: (ratio, lower, upper). expected must be above zero."""
    if not _positive(expected):
        raise ValueError("expected must be above zero")
    lo, hi = poisson_interval(observed)
    return observed / expected, lo / expected, hi / expected


def small_number_flags(cases, populations, min_population=None, min_cases=DEFAULT_MIN_CASES):
    """Per area: None when the figure is stable enough to show, else 'cases below N', 'population below N' or both."""
    flags = []
    for c, p in zip(cases, populations, strict=True):
        reasons = []
        if c < min_cases:
            reasons.append(f"cases below {min_cases}")
        if min_population is not None and p < min_population:
            reasons.append(f"population below {min_population:g}")
        flags.append(" and ".join(reasons) if reasons else None)
    return flags


def eb_global(cases, populations, per=DEFAULT_PER):
    """Global empirical-Bayes smoothed rates (Marshall 1991). Each area's rate r_i is pulled toward the overall rate m by a weight that grows with its population:
        s2 = sum p_i (r_i - m)^2 / sum p_i  -  m / mean(p)        (the between-area variance after removing the Poisson noise; floored at 0)
        W_i = s2 / (s2 + m / p_i)          smoothed_i = W_i r_i + (1 - W_i) m
    Returns {'rates': [smoothed per `per`], 'weights': [W_i], 'overall': m per `per`, 'between_variance': s2 per-unit squared}. When s2 is 0 or below (areas differ no more than Poisson noise explains) every area takes the overall rate.
    Known answer: two areas with the same rate are unchanged (s2 is negative, so both take the overall rate, which equals theirs)."""
    check_inputs(cases, populations, per=per)
    total_pop = float(sum(populations))
    m = sum(cases) / total_pop
    raw = [c / p for c, p in zip(cases, populations, strict=True)]
    mean_pop = total_pop / len(populations)
    s2 = sum(p * (r - m) ** 2 for p, r in zip(populations, raw, strict=True)) / total_pop - m / mean_pop
    s2 = max(s2, 0.0)
    weights = [s2 / (s2 + m / p) if s2 > 0 else 0.0 for p in populations]
    smoothed = [w * r + (1 - w) * m for w, r in zip(weights, raw, strict=True)]
    return {"rates": [v * per for v in smoothed], "weights": weights, "overall": m * per, "between_variance": s2}


def analyse(cases, populations, method="crude", expected=None, per=DEFAULT_PER, min_population=None, min_cases=DEFAULT_MIN_CASES):
    """One call for the tool. Returns {'areas': [{'rate', 'rate_lo', 'rate_hi', 'rel_risk', 'smr', 'smr_lo', 'smr_hi', 'expected', 'eb_rate', 'eb_weight', 'value', 'flag'}], 'overall_rate', 'per', 'method', 'flagged', 'between_variance'}.
    `value` is the headline figure for `method` (crude rate, SMR, or smoothed rate); `flag` is the small-number reason or None. method 'smr' needs `expected` and refuses without it: this tool never invents expected counts."""
    method = str(method or "crude").strip().lower()
    if method not in METHODS:
        raise ValueError(f"method must be one of {', '.join(METHODS)}")
    if method == "smr" and expected is None:
        raise ValueError("method 'smr' needs expected counts (expected_field): the right expected count comes from reference rates for your age and sex groups, which this tool does not invent")
    check_inputs(cases, populations, expected, per, min_population, min_cases)
    overall = sum(cases) / float(sum(populations))
    flags = small_number_flags(cases, populations, min_population, min_cases)
    eb = eb_global(cases, populations, per)
    areas = []
    for i, (c, p) in enumerate(zip(cases, populations, strict=True)):
        lo, hi = poisson_interval(c)
        rate = crude_rate(c, p, per)
        row = {"rate": rate, "rate_lo": lo / p * per, "rate_hi": hi / p * per, "rel_risk": (c / p) / overall, "smr": None, "smr_lo": None, "smr_hi": None, "expected": None,
               "eb_rate": eb["rates"][i], "eb_weight": eb["weights"][i], "flag": flags[i]}
        if expected is not None:
            ratio, slo, shi = smr(c, expected[i])
            row.update(smr=ratio, smr_lo=slo, smr_hi=shi, expected=float(expected[i]))
        row["value"] = {"crude": row["rate"], "smr": row["smr"], "eb": row["eb_rate"]}[method]
        areas.append(row)
    return {"areas": areas, "overall_rate": overall * per, "per": per, "method": method, "flagged": sum(1 for f in flags if f), "between_variance": eb["between_variance"]}
