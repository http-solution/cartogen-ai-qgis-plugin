"""Persona style profiles, layer L2 of the styling plan (PLAN-023 R1-7): a pure registry `{profile id: {role: spec}}` that only supplies CHOICES (palette family, class count, label units and the convention
behind them). The existing styling modules still draw; nothing calls this registry yet, so no map changes until a later package (for example R3-6) reads it. Layer order (docs/PERSONA_TOOLS_STYLING_PLAN_2026-10-04.md
section 5): L0 global rules, L1 role defaults, L2 this registry, and a user's remembered per-project style beats all of them.

Roles (what the colours are for):
  categorical  classes of things (land use, vehicle, mode)              -> a CATEGORICAL palette
  intensity    one quantity from low to high (rate, cost band, hazard)  -> a SEQUENTIAL ramp
  difference   change or deviation around a neutral middle              -> a DIVERGING ramp

Rules, enforced by tests/test_style_profiles.py (not by this module):
  * categorical palettes: every neighbouring pair stays at CIEDE2000 >= 10 in normal vision and after simulating deuteranopia, protanopia and tritanopia (core/representation/colour_rules.py);
  * every palette: no red beside green;
  * a ramp's neighbouring steps stay at CIEDE2000 >= 5 (our own floor for ramps, lower than the categorical one because steps of one hue are meant to look alike).
Limits, stated plainly: the rules look at neighbours in PALETTE order, which is also the legend order; two categories drawn next to each other on the map can be any pair. The simulation models average dichromatic vision.

Palette sources: Okabe and Ito (2008) colour-blind-safe set, re-ordered here so neighbours pass the rules; ColorBrewer (Brewer) 5-class sequential and diverging ramps; the utility colour code is OUR screen approximation of the APWA uniform
colour code (the standard defines paint colours, not screen values). Where a published palette has not been chosen yet the spec says status 'placeholder' and why."""

PALETTES = {
    "okabe_ito": {"kind": "categorical", "source": "Okabe and Ito 2008, re-ordered", "colours": ["#E69F00", "#000000", "#F0E442", "#0072B2", "#D55E00", "#56B4E9", "#CC79A7", "#009E73"]},
    "utility_colour_code": {"kind": "categorical", "source": "approximation of the APWA uniform colour code for screens (water, sewer, gas, electric, communications, reclaimed)",
                            "colours": ["#0066CC", "#2E8B57", "#F2D600", "#E00000", "#F28C00", "#7B3FA0"],
                            "labels": ["water", "sewer", "gas", "electric", "communications", "reclaimed water"]},
    # R3-6. The official ESA WorldCover legend: colours fixed by the published product (2020 v100 and 2021 v200 use the same legend), so they are NOT altered to pass the colour-blind rule. Instead the weak pairs are
    # recorded in `known_weak` (every pair under CIEDE2000 10 in normal vision or a simulated deficiency, not only neighbours) and a test keeps that record exact; the look always puts the class NAME in the legend, never colour alone.
    "esa_worldcover": {"kind": "categorical", "source": "ESA WorldCover legend (official class colours)", "standard": True,
                       "codes": [10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100],
                       "labels": ["Tree cover", "Shrubland", "Grassland", "Cropland", "Built-up", "Bare / sparse vegetation", "Snow and ice", "Permanent water bodies", "Herbaceous wetland", "Mangroves", "Moss and lichen"],
                       "colours": ["#006400", "#FFBB22", "#FFFF4C", "#F096FF", "#FA0000", "#B4B4B4", "#F0F0F0", "#0064C8", "#0096A0", "#00CF75", "#FAE6A0"],
                       "known_weak": [["Tree cover", "Built-up", "protanopia"], ["Shrubland", "Mangroves", "protanopia"], ["Grassland", "Snow and ice", "tritanopia"], ["Mangroves", "Moss and lichen", "protanopia"]]},
    # our own choice (not a published standard): orange for loss and purple for gain, so neither is red or green
    "change_classes": {"kind": "categorical", "source": "Cartogen AI choice: loss, stable, gain without red or green", "codes": [-1, 0, 1], "labels": ["loss", "stable", "gain"], "colours": ["#E66101", "#CCCCCC", "#5E3C99"]},
    "Blues": {"kind": "sequential", "source": "ColorBrewer", "colours": ["#EFF3FF", "#BDD7E7", "#6BAED6", "#3182BD", "#08519C"]},
    "YlOrRd": {"kind": "sequential", "source": "ColorBrewer", "colours": ["#FFFFB2", "#FECC5C", "#FD8D3C", "#F03B20", "#BD0026"]},
    "Greens": {"kind": "sequential", "source": "ColorBrewer", "colours": ["#EDF8E9", "#BAE4B3", "#74C476", "#31A354", "#006D2C"]},
    "Greys": {"kind": "sequential", "source": "ColorBrewer", "colours": ["#F7F7F7", "#CCCCCC", "#969696", "#636363", "#252525"]},
    "PuBu": {"kind": "sequential", "source": "ColorBrewer", "colours": ["#F1EEF6", "#BDC9E1", "#74A9CF", "#2B8CBE", "#045A8D"]},
    "RdBu": {"kind": "diverging", "source": "ColorBrewer", "colours": ["#CA0020", "#F4A582", "#F7F7F7", "#92C5DE", "#0571B0"]},
    "BrBG": {"kind": "diverging", "source": "ColorBrewer", "colours": ["#A6611A", "#DFC27D", "#F5F5F5", "#80CDC1", "#018571"]},
    "PuOr": {"kind": "diverging", "source": "ColorBrewer", "colours": ["#E66101", "#FDB863", "#F7F7F7", "#B2ABD2", "#5E3C99"]},
}

ROLES = ("categorical", "intensity", "difference")
ROLE_KIND = {"categorical": "categorical", "intensity": "sequential", "difference": "diverging"}
DEFAULT_PROFILE = "general"


def _spec(palette, classes, units=None, convention="", status="chosen", reason=""):
    return {"palette": palette, "classes": classes, "label_units": units, "convention": convention, "status": status, "reason": reason}


def _profile(categorical=None, intensity=None, difference=None):
    base = {"categorical": _spec("okabe_ito", 6, convention="Okabe-Ito, colour-blind safe"), "intensity": _spec("Blues", 5), "difference": _spec("RdBu", 5, convention="blue beside red, never red beside green")}
    return {role: given or base[role] for role, given in (("categorical", categorical), ("intensity", intensity), ("difference", difference))}


# Each profile follows the 'Map looks to add' table of the styling plan; a convention string says which line of it a choice comes from.
PROFILES = {
    "general": _profile(),
    "humanitarian": _profile(intensity=_spec("YlOrRd", 5, "severity class 1-5", "severity 1-5 ramp, the same classes on every map; IASC cluster colours stay in apply_categorized_style")),
    "engineering": _profile(intensity=_spec("Greys", 5, "m", "terrain and elevation under contours and hillshade"), difference=_spec("PuOr", 5, "m", "cut and fill as one diverging raster, orange and purple so neither is red or green")),
    "urban_planning": _profile(categorical=_spec("okabe_ito", 6, convention="land use categories", status="placeholder", reason="the plan says a published land-use palette is still to be chosen; this is the colour-blind-safe default until it is"),
                               intensity=_spec("YlOrRd", 5, convention="heat ramp")),
    "logistics": _profile(categorical=_spec("okabe_ito", 6, convention="one colour per vehicle route"), intensity=_spec("YlOrRd", 5, "minutes", "cost bands")),
    "agriculture": _profile(intensity=_spec("Greens", 5, None, "management zones of 3 to 5 sequential classes; the legend states the rate unit the user supplied, so no unit is fixed here"),
                            difference=_spec("BrBG", 5, convention="index anomaly, brown to blue-green")),
    "environment": _profile(categorical=_spec("okabe_ito", 6, convention="land-cover classes", status="placeholder", reason="official land-cover palettes (ESA WorldCover, CORINE) are to be selectable; they are not in the registry yet (R3-6)"),
                            difference=_spec("PuOr", 3, convention="loss, stable, gain: orange, neutral, purple")),
    "public_health": _profile(intensity=_spec("Blues", 5, "per 100,000", "single-hue sequential rate map; cluster outlines in a non-red contrasting colour; suppressed small numbers are hatched, never coloured"),
                              difference=_spec("RdBu", 5, convention="relative risk around 1")),
    "disaster_risk": _profile(intensity=_spec("YlOrRd", 5, convention="hazard intensity; the legend carries the scenario name and assumptions")),
    "utilities": _profile(categorical=_spec("utility_colour_code", 6, convention="APWA uniform colour code as a default setting the user can change")),
    "transport": _profile(intensity=_spec("PuBu", 5, "minutes", "isochrone bands")),
    "public_safety": _profile(intensity=_spec("YlOrRd", 5, convention="density surface; the legend states the bandwidth")),
    "research": _profile(intensity=_spec("Greys", 5, convention="greyscale-safe ramp for publication figures")),
    "real_estate": _profile(intensity=_spec("PuBu", 5, "minutes", "trade-area bands")),
}


def profile_ids():
    return list(PROFILES)


def spec(profile_id, role):
    """The spec for a profile and role; an unknown or missing profile reads as `general`, an unknown role raises ValueError. A copy, so callers cannot change the registry."""
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}; roles are {', '.join(ROLES)}")
    return dict(PROFILES.get(profile_id) or PROFILES[DEFAULT_PROFILE])[role].copy()


def colours(palette_name):
    """The hex colours of a palette, in palette (legend) order; ValueError for an unknown palette."""
    if palette_name not in PALETTES:
        raise ValueError(f"unknown palette {palette_name!r}")
    return list(PALETTES[palette_name]["colours"])
