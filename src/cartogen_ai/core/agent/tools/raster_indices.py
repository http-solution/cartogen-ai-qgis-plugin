"""Spectral index formulas (PLAN-023 R3-1): pure numpy, no QGIS and no GDAL, so every formula is checked by hand-computed known answers offline.

Each index is a function of named band roles (nir, red, ...) and returns the index plus the mask of cells where it is defined. A cell is undefined
(NoData, never 0) where an input band is NoData or not finite, or where the formula's denominator is exactly zero.

Formulas, with the sources they are standard in:
  NDVI  = (NIR - Red) / (NIR + Red)                                Rouse et al. 1974
  NDWI  = (Green - NIR) / (Green + NIR)                            McFeeters 1996 (open water)
  MNDWI = (Green - SWIR1) / (Green + SWIR1)                        Xu 2006
  NDRE  = (NIR - RedEdge) / (NIR + RedEdge)                        Gitelson and Merzlyak 1994
  NDMI  = (NIR - SWIR1) / (NIR + SWIR1)                            Gao 1996 (vegetation moisture)
  NBR   = (NIR - SWIR2) / (NIR + SWIR2)                            Key and Benson 2006 (burn ratio)
  SAVI  = (NIR - Red) / (NIR + Red + L) x (1 + L), L = 0.5         Huete 1988
  EVI   = 2.5 x (NIR - Red) / (NIR + 6 Red - 7.5 Blue + 1)         Huete et al. 2002 (reflectance scaled 0 to 1)
  BSI   = ((SWIR1 + Red) - (NIR + Blue)) / ((SWIR1 + Red) + (NIR + Blue))   Rikimaru et al. 2002 (bare soil)
The band-to-role assignment is the caller's: a sensor's band numbers differ (Sentinel-2 B8 is NIR, Landsat 8 band 5 is). Nothing here guesses which
band is which, and EVI assumes reflectance already scaled to 0..1 (a raster in digital numbers gives a meaningless EVI; the tool says so)."""

SOIL_FACTOR_DEFAULT = 0.5

# index -> (band roles in the order they are documented, formula text for the result, what the value means in one line)
INDICES = {
    "NDVI": (("nir", "red"), "(NIR - Red) / (NIR + Red)", "vegetation greenness and density"),
    "NDWI": (("green", "nir"), "(Green - NIR) / (Green + NIR)", "open surface water"),
    "MNDWI": (("green", "swir1"), "(Green - SWIR1) / (Green + SWIR1)", "open surface water, less confused by built-up areas"),
    "NDRE": (("nir", "rededge"), "(NIR - RedEdge) / (NIR + RedEdge)", "crop chlorophyll, sensitive at high canopy density"),
    "NDMI": (("nir", "swir1"), "(NIR - SWIR1) / (NIR + SWIR1)", "vegetation water content"),
    "NBR": (("nir", "swir2"), "(NIR - SWIR2) / (NIR + SWIR2)", "burned area and burn severity (compare before and after)"),
    "SAVI": (("nir", "red"), "(NIR - Red) / (NIR + Red + L) x (1 + L)", "vegetation where bare soil shows through"),
    "EVI": (("nir", "red", "blue"), "2.5 x (NIR - Red) / (NIR + 6 Red - 7.5 Blue + 1)", "vegetation in dense canopy (reflectance scaled 0 to 1)"),
    "BSI": (("blue", "red", "nir", "swir1"), "((SWIR1 + Red) - (NIR + Blue)) / ((SWIR1 + Red) + (NIR + Blue))", "bare soil"),
}


NORMALISED_DIFFERENCE = ("NDVI", "NDWI", "MNDWI", "NDRE", "NDMI", "NBR")      # (first - second) / (first + second), roles in INDICES order


def _np():
    import numpy as np
    return np


def roles_for(index):
    """The band roles `index` needs, in documented order, or None for an unknown index. Pure."""
    entry = INDICES.get(str(index or "").strip().upper())
    return entry[0] if entry else None


def normalise_name(index):
    """The canonical upper-case index name, or None when it is not supported. Pure."""
    name = str(index or "").strip().upper()
    return name if name in INDICES else None


def describe(index):
    """{'formula', 'meaning', 'roles'} for a supported index, else None. Pure."""
    name = normalise_name(index)
    if name is None:
        return None
    roles, formula, meaning = INDICES[name]
    return {"formula": formula, "meaning": meaning, "roles": list(roles)}


def _ratio(numerator, denominator, valid):
    """numerator / denominator where defined: NoData (not 0) where the denominator is exactly zero."""
    np = _np()
    ok = valid & (denominator != 0)
    out = np.zeros(numerator.shape, dtype=np.float64)
    np.divide(numerator, denominator, out=out, where=ok)
    return out, ok


def compute_index(index, bands, valid, soil_factor=SOIL_FACTOR_DEFAULT):
    """(values float32, defined mask) for `index` from `bands` {role: 2-D array}, restricted to the cells in `valid`. Raises ValueError for an unknown
    index or a missing band role. Values in undefined cells are 0 and must be written as NoData by the caller. Pure numpy."""
    np = _np()
    name = normalise_name(index)
    if name is None:
        raise ValueError(f"'{index}' is not a supported index. Supported: {', '.join(INDICES)}.")
    missing = [r for r in INDICES[name][0] if r not in bands]
    if missing:
        raise ValueError(f"{name} needs the band roles {', '.join(INDICES[name][0])}; missing: {', '.join(missing)}.")
    b = {role: np.asarray(arr, dtype=np.float64) for role, arr in bands.items()}
    valid = np.asarray(valid, dtype=bool)
    for arr in b.values():
        valid = valid & np.isfinite(arr)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        if name in NORMALISED_DIFFERENCE:
            first, second = INDICES[name][0]
            values, ok = _ratio(b[first] - b[second], b[first] + b[second], valid)
        elif name == "SAVI":
            ell = float(soil_factor)
            values, ok = _ratio((b["nir"] - b["red"]) * (1.0 + ell), b["nir"] + b["red"] + ell, valid)
        elif name == "EVI":
            values, ok = _ratio(2.5 * (b["nir"] - b["red"]), b["nir"] + 6.0 * b["red"] - 7.5 * b["blue"] + 1.0, valid)
        else:  # BSI
            swir_red = b["swir1"] + b["red"]
            nir_blue = b["nir"] + b["blue"]
            values, ok = _ratio(swir_red - nir_blue, swir_red + nir_blue, valid)
    ok = ok & np.isfinite(values)
    return np.where(ok, values, 0.0).astype(np.float32), ok


SCALE_SENSITIVE = ("EVI", "SAVI")      # not scale-invariant: SAVI adds L and EVI adds 1, both meant for reflectance between 0 and 1
REFLECTANCE_LIMIT = 1.5                # a reflectance band stays below this; digital numbers (0 to 10000 or 255) are far above it


def scale_note(index, band_max):
    """A warning sentence when `index` is scale-sensitive and the largest input value looks like digital numbers instead of reflectance, else ''. Pure.

    The normalised differences (NDVI and the rest) give the same answer at any scale, so they are never warned about."""
    name = normalise_name(index)
    if name in SCALE_SENSITIVE and band_max > REFLECTANCE_LIMIT:
        return (f"The largest input value is {band_max:g}, which looks like digital numbers, not reflectance between 0 and 1. {name} adds a constant "
                "that assumes reflectance, so this result is not meaningful; scale the bands to reflectance first (for Sentinel-2 L2A divide by 10000, "
                "after any offset the product states), then run it again.")
    return ""


def parse_band_ref(text):
    """(layer name, band number) from 'layer name' (band 1) or 'layer name@3' (band 3, the same form raster_calculator uses). Returns (None, None)
    for anything else, including a band number below 1. Pure."""
    raw = str(text or "").strip()
    if not raw:
        return None, None
    name, sep, tail = raw.rpartition("@")
    if sep and tail.strip().isdigit():
        band = int(tail.strip())
        return (name.strip(), band) if name.strip() and band >= 1 else (None, None)
    return raw, 1


def check_bands(index, bands):
    """Error text when `bands` {role: reference} does not match what `index` needs (a missing role, an unknown role, an empty reference), else None. Pure."""
    name = normalise_name(index)
    if name is None:
        return f"'{index}' is not a supported index. Supported: {', '.join(INDICES)}."
    if not isinstance(bands, dict) or not bands:
        return f"{name} needs the bands argument: {{role: layer name}} for the roles {', '.join(INDICES[name][0])}."
    wanted = INDICES[name][0]
    missing = [r for r in wanted if not str(bands.get(r) or "").strip()]
    extra = [r for r in bands if r not in wanted]
    if missing:
        return f"{name} needs a layer for each of: {', '.join(wanted)}. Missing: {', '.join(missing)}."
    if extra:
        return f"{name} does not use the band role(s) {', '.join(map(str, extra))}; it uses {', '.join(wanted)}."
    return None
