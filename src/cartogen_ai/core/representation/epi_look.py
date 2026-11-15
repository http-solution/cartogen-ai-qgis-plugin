"""The public-health look (PLAN-023 R2-5), pure Python: no Qt and no QGIS. It decides WHAT a rate map, a cluster outline and a hot-spot or LISA map look like; the tool apply_public_health_look draws it, so the classes,
the colours and the legend words cannot drift from what is tested here.

Rules, enforced by tests/test_epi_look.py:
  * rate: one hue (the style registry's public_health intensity ramp, ColorBrewer Blues, 5 classes), classes from the QUANTILES of the figures that are shown, never fewer distinct values than classes (a class that would
    be empty or repeat another is dropped, and the reply says so);
  * suppressed figures (small numbers) are drawn as a grey hatch, never coloured by a class, and the legend says 'suppressed where n < N';
  * cluster outlines: a black line with a narrower white line on top (a double stroke, readable on any fill), no fill, and never red: red already means 'alarm' on most maps and would turn a statistical circle into a warning;
  * hot spots, cold spots and LISA classes use the ColorBrewer PuOr diverging colours (brown-orange for high, purple for low), so no class is red or green and none is red beside green.
Limits, stated plainly: the colours are checked by the repo's colour rules (neighbour distance and red-beside-green); the hatch is a brush pattern whose line spacing is Qt's, not a published standard."""
from . import colour_rules, style_looks, style_profiles

PROFILE = "public_health"
DEFAULT_MIN_CASES = 5
LOOKS = ("rate", "cluster", "lisa", "hotspot")
SUPPRESSED_COLOUR = "#7F7F7F"
SUPPRESSED_HATCH = {"kind": "brush_pattern", "brush": "BDiagPattern", "colour": SUPPRESSED_COLOUR, "outline_colour": SUPPRESSED_COLOUR, "outline_width_mm": 0.2}
CLUSTER_STROKES = (                 # drawn in this order, so the white line sits on the black one
    {"colour": "#000000", "width_mm": 1.2},
    {"colour": "#FFFFFF", "width_mm": 0.5},
)
NOT_SIGNIFICANT_COLOUR = "#F7F7F7"
NO_NEIGHBOURS_COLOUR = "#BDBDBD"
# ColorBrewer PuOr, 7 classes: strong to weak orange, the neutral middle, weak to strong purple. One deliberate change: ColorBrewer's lightest purple (#D8DAEB) sits only 9.8 (CIEDE2000, normal vision) and 7.1
# (tritanopia) from the neutral 'not significant' colour, under the repo's floor of 10, so the 90% cold class is the slightly darker #C6C8E2 (11.3 or more in every vision type).
LISA_CLASSES = (("HH", "#B35806", "High among high"), ("HL", "#F1A340", "High among low"), ("LH", "#998EC3", "Low among high"), ("LL", "#542788", "Low among low"),
                ("not significant", NOT_SIGNIFICANT_COLOUR, "Not significant"), ("no neighbours", NO_NEIGHBOURS_COLOUR, "No neighbours"))
HOTSPOT_CLASSES = (("Hot spot 99%", "#B35806", "Hot spot 99%"), ("Hot spot 95%", "#F1A340", "Hot spot 95%"), ("Hot spot 90%", "#FEE0B6", "Hot spot 90%"),
                   ("Not significant", NOT_SIGNIFICANT_COLOUR, "Not significant"),
                   ("Cold spot 90%", "#C6C8E2", "Cold spot 90%"), ("Cold spot 95%", "#998EC3", "Cold spot 95%"), ("Cold spot 99%", "#542788", "Cold spot 99%"),
                   ("No neighbours", NO_NEIGHBOURS_COLOUR, "No neighbours"))


def legend_title(per=100000, min_cases=DEFAULT_MIN_CASES):
    """The sentence a rate legend carries. Known answer: 'Rate per 100,000; suppressed where n < 5'."""
    return f"Rate per {per:,.0f}; suppressed where n < {min_cases}"


def quantile(sorted_values, q):
    """The q quantile (0 to 1) of an ascending list, by linear interpolation between the closest ranks (the common 'type 7' rule). ValueError for an empty list."""
    if not sorted_values:
        raise ValueError("no values")
    position = (len(sorted_values) - 1) * q
    lower = int(position // 1)
    upper = min(lower + 1, len(sorted_values) - 1)
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * (position - lower)


def _label_number(value):
    if abs(value) >= 100:
        return f"{value:,.0f}"
    return f"{value:,.1f}"


def rate_classes(values, classes=5):
    """Quantile classes for the figures that are SHOWN (None and NaN are the suppressed ones and are ignored). Returns {'classes': [{'lo', 'hi', 'label', 'colour'}], 'dropped': n, 'shown': count}.
    Break points that repeat (many equal figures) are merged, so there are never empty or duplicate classes: 'dropped' says how many of the requested classes were lost. Known answer: 1..100 in 5 classes
    breaks at 1, 20.8, 40.6, 60.4, 80.2, 100. ValueError when nothing is shown, or classes is not 2 to 5."""
    if isinstance(classes, bool) or not isinstance(classes, int) or not 2 <= classes <= 5:
        raise ValueError("classes must be 2 to 5 (a rate ramp of more steps cannot be told apart)")
    shown = sorted(float(v) for v in values if v is not None and v == v)
    if not shown:
        raise ValueError("no figure is shown (every area is suppressed or empty), so there is nothing to colour by rate")
    breaks = [quantile(shown, i / classes) for i in range(classes + 1)]
    merged = [breaks[0]]
    for b in breaks[1:]:
        if b > merged[-1]:
            merged.append(b)
    if len(merged) < 2:
        merged = [merged[0], merged[0]]               # every figure is the same: one class holding all of them
    count = len(merged) - 1
    palette = style_looks.ramp_steps(style_profiles.spec(PROFILE, "intensity")["palette"], classes)
    if count < classes:                               # keep the darkest and lightest ends when classes were dropped
        palette = [palette[round(i * (classes - 1) / (count - 1))] for i in range(count)] if count > 1 else [palette[-1]]
    out = []
    for i in range(count):
        lo, hi = merged[i], merged[i + 1]
        out.append({"lo": lo, "hi": hi, "label": f"{_label_number(lo)} to {_label_number(hi)}", "colour": palette[i]})
    return {"classes": out, "dropped": classes - count, "shown": len(shown)}


def class_for(value, classes):
    """The class a shown figure falls in (lo <= value < hi, the last class includes its top), or None for a suppressed one. Used to check the renderer's rules against the same logic."""
    if value is None or value != value:
        return None
    for i, c in enumerate(classes):
        last = i == len(classes) - 1
        if c["lo"] <= value < c["hi"] or (last and value == c["hi"]) or (c["lo"] == c["hi"] == value):
            return c
    return None


def category_entries(look):
    """[(value, colour, legend label)] for the 'lisa' or 'hotspot' look; ValueError otherwise."""
    if look == "lisa":
        return list(LISA_CLASSES)
    if look == "hotspot":
        return list(HOTSPOT_CLASSES)
    raise ValueError(f"look {look!r} has no category table")


def all_colours():
    """Every colour this look can draw, for the colour rules."""
    colours = {c["colour"] for c in rate_classes(range(1, 101))["classes"]}
    colours |= {SUPPRESSED_COLOUR, NOT_SIGNIFICANT_COLOUR, NO_NEIGHBOURS_COLOUR} | {s["colour"] for s in CLUSTER_STROKES}
    colours |= {c for _v, c, _l in LISA_CLASSES} | {c for _v, c, _l in HOTSPOT_CLASSES}
    return sorted(colours)


def any_red(colours):
    return [c for c in colours if colour_rules.is_red(c)]
