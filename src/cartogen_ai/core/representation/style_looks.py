"""Named looks for the agriculture and environment personas (PLAN-023 R3-6), pure Python, no Qt and no QGIS. They sit on top of the style registry (style_profiles.py: palettes and per-role choices) and only supply CHOICES: which colour for which class, which
legend words, how many classes. Drawing them on a layer is done by the tool apply_land_cover_look and the layout templates; nothing here touches QGIS, so every rule below is tested offline.

What is and is not claimed:
  * ESA WorldCover: the colours and class names are the official legend, used unchanged; their colour-blind weaknesses are recorded in the palette, not hidden.
  * change classes loss, stable and gain: our own choice (orange, grey, purple), not a published standard.
  * index classes (NDVI, NDWI, NDRE): equal-interval DISPLAY breaks over a stated display range, labelled with the index and its units. They are not agronomic thresholds and carry no meaning such as 'stressed' or 'healthy'.
  * management zones: 3 to 5 sequential classes labelled with the mean index of each zone. The legend never states a yield, a rate or a recommendation.
  * protected-area hatch: a brush pattern for a polygon layer. It says where a layer is, not that the area is protected in law; the legend names the layer it came from."""
import itertools

from . import style_profiles

INDEX_DISPLAY = {
    # index: (palette, display low, display high, units text). Index values are ratios of band reflectances, so they have no physical unit.
    "NDVI": ("Greens", 0.0, 1.0, "index value, unitless"),
    "NDRE": ("Greens", 0.0, 1.0, "index value, unitless"),
    "NDWI": ("Blues", -1.0, 1.0, "index value, unitless"),
}
MIN_INDEX_CLASSES, MAX_INDEX_CLASSES = 3, 7
MIN_ZONES, MAX_ZONES = 3, 5
ZONE_PALETTE = "Greens"
HATCHES = {
    # a simple-fill brush pattern (Qt BrushStyle name), the same mechanism set_layer_symbol uses for 'hatch_forward': forward diagonal lines in one colour with an outline. Line spacing is the brush's own and is not settable.
    "protected_area": {"kind": "brush_pattern", "brush": "BDiagPattern", "colour": "#404040", "outline_colour": "#404040", "outline_width_mm": 0.3},
}
LOOKS = {
    "agriculture": {
        "index_classes": {"indices": sorted(INDEX_DISPLAY), "default_classes": 5, "note": "equal-interval display breaks, not agronomic thresholds"},
        "management_zones": {"min_classes": MIN_ZONES, "max_classes": MAX_ZONES, "palette": ZONE_PALETTE, "legend": "mean index value of each zone", "note": "the legend never states a yield, a rate or a recommendation"},
    },
    "environment": {
        "land_cover": {"palette": "esa_worldcover"},
        "change_classes": {"palette": "change_classes"},
        "protected_area": {"hatch": "protected_area"},
    },
}


def ramp_steps(palette_name, count):
    """`count` colours picked evenly, ends included, from a sequential or diverging palette. ValueError for a count under 2 or over the palette's own number of colours."""
    colours = style_profiles.colours(palette_name)
    if not 2 <= count <= len(colours):
        raise ValueError(f"{palette_name} has {len(colours)} colours; asked for {count}")
    return [colours[round(i * (len(colours) - 1) / (count - 1))] for i in range(count)]


def index_breaks(index, classes=5):
    """Equal-interval break values between the display low and high of an index, `classes` - 1 of them, rounded to 2 decimals."""
    _palette, low, high, _units = _index(index)
    if not MIN_INDEX_CLASSES <= classes <= MAX_INDEX_CLASSES:
        raise ValueError(f"index classes must be {MIN_INDEX_CLASSES} to {MAX_INDEX_CLASSES}, not {classes}")
    step = (high - low) / classes
    return [round(low + step * i, 2) for i in range(1, classes)]


def _index(index):
    key = str(index or "").strip().upper()
    if key not in INDEX_DISPLAY:
        raise ValueError(f"unknown index {index!r}; known: {', '.join(sorted(INDEX_DISPLAY))}")
    return INDEX_DISPLAY[key]


def _number(value):
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def index_class_labels(index, breaks=None):
    """Legend labels for the classes between `breaks`: 'below 0.2', '0.2 to 0.4', ..., '0.8 and above'. Ranges only, no meaning."""
    breaks = list(breaks) if breaks is not None else index_breaks(index)
    if any(b2 <= b1 for b1, b2 in itertools.pairwise(breaks)):
        raise ValueError("breaks must increase")
    edges = [f"below {_number(breaks[0])}"]
    edges += [f"{_number(a)} to {_number(b)}" for a, b in itertools.pairwise(breaks)]
    edges.append(f"{_number(breaks[-1])} and above")
    return edges


def index_look(index, classes=5):
    """{'title', 'units', 'breaks', 'classes': [{'label', 'colour'}]} for an index: legend title with its units, and one colour per class from the index's palette."""
    palette, _low, _high, units = _index(index)
    breaks = index_breaks(index, classes)
    colours = ramp_steps(palette, classes) if classes <= len(style_profiles.colours(palette)) else None
    if colours is None:
        raise ValueError(f"{palette} has too few colours for {classes} classes")
    labels = index_class_labels(index, breaks)
    return {"index": str(index).upper(), "title": f"{str(index).upper()} ({units})", "units": units, "breaks": breaks, "classes": [{"label": lab, "colour": col} for lab, col in zip(labels, colours, strict=True)]}


def zone_look(index, means):
    """Legend for management zones. `means` is the mean index value of each zone (3 to 5 of them). Zones are put in ascending order of mean so the sequential colours run light to dark with the value; each label states its mean, never a rate or a yield.
    Returns [{'label', 'colour', 'mean'}]."""
    values = list(means)
    if not MIN_ZONES <= len(values) <= MAX_ZONES:
        raise ValueError(f"management zones must be {MIN_ZONES} to {MAX_ZONES}, not {len(values)}")
    _index(index)
    colours = ramp_steps(ZONE_PALETTE, len(values))
    ordered = sorted(float(v) for v in values)
    return [{"label": f"Zone {i}: mean {str(index).upper()} {v:.2f}", "colour": colours[i - 1], "mean": v} for i, v in enumerate(ordered, 1)]


def worldcover_entries():
    """[{'code', 'label', 'colour'}] for the official ESA WorldCover legend, in code order."""
    palette = style_profiles.PALETTES["esa_worldcover"]
    return [{"code": c, "label": lab, "colour": col} for c, lab, col in zip(palette["codes"], palette["labels"], palette["colours"], strict=True)]


def change_entries():
    palette = style_profiles.PALETTES["change_classes"]
    return [{"code": c, "label": lab, "colour": col} for c, lab, col in zip(palette["codes"], palette["labels"], palette["colours"], strict=True)]


def _lookup(entries, value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(str(value).strip())
        if number == int(number):
            return next((e for e in entries if e["code"] == int(number)), None)
        return None
    except ValueError:
        pass
    text = str(value).strip().lower()
    return next((e for e in entries if e["label"].lower() == text), None)


def worldcover_lookup(value):
    """The WorldCover entry for a class code (10, '10', 10.0) or an official class name (any letter case), else None."""
    return _lookup(worldcover_entries(), value)


def change_lookup(value):
    """The change entry for -1, 0, 1 (or the same as text) or for 'loss', 'stable', 'gain', else None."""
    return _lookup(change_entries(), value)


def legend_labels(entries):
    """Legend text for entries: 'Tree cover (10)'. The class NAME is always there, so a colour is never the only carrier of the meaning."""
    return [f"{e['label']} ({e['code']})" for e in entries]
