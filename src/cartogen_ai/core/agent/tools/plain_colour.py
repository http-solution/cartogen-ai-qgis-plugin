# -*- coding: utf-8 -*-
"""Plain-language colour words -> hex, Qt-free so it is unit-testable without QGIS.

Why: change_layer_color and the symbol styles only accepted what QColor parses ("#cc0000", "darkred"). A person asks for "dark
red", "pale yellow" or "light blue"; QColor rejects those (it knows "darkred", not "dark red"), so a plain request ended in an
"Invalid color" error unless the model happened to translate the words to hex itself. This resolves the everyday vocabulary
deterministically. Anything it does not recognise returns None and the caller falls back to QColor, so nothing that worked before
changes.
"""
import re

_BASE = {
    "red": "#d7191c", "orange": "#fd8d3c", "yellow": "#ffd92f", "green": "#31a354", "blue": "#2b83ba", "purple": "#756bb1",
    "pink": "#f768a1", "brown": "#8c510a", "black": "#000000", "white": "#ffffff", "grey": "#969696", "gray": "#969696",
    "cyan": "#17becf", "teal": "#1b9e77", "navy": "#08306b", "maroon": "#800000", "beige": "#f5f5dc", "gold": "#e6ab02",
    "olive": "#808000", "lime": "#a6d854", "magenta": "#d01c8b", "turquoise": "#40e0d0", "violet": "#8856a7", "tan": "#d2b48c",
    "sand": "#e0c9a6", "cream": "#fffdd0", "amber": "#ffbf00", "crimson": "#dc143c", "scarlet": "#ff2400", "indigo": "#4b0082",
}
# Each modifier moves the colour toward white (positive) or black (negative) by that fraction.
_SHADE = {"light": 0.45, "pale": 0.7, "soft": 0.5, "pastel": 0.6, "dark": -0.4, "deep": -0.25, "bright": 0.0, "vivid": 0.0, "strong": 0.0}


def _mix(hex_value, amount):
    r, g, b = (int(hex_value[i:i + 2], 16) for i in (1, 3, 5))
    target = 255 if amount > 0 else 0
    f = abs(amount)
    return "#{:02x}{:02x}{:02x}".format(*(round(c + (target - c) * f) for c in (r, g, b)))


def resolve_colour(text):
    """Return '#rrggbb' for a hex code or an everyday colour phrase ("dark red", "pale-yellow"), else None."""
    if not isinstance(text, str):
        return None
    t = text.strip().lower()
    if re.fullmatch(r"#[0-9a-f]{6}", t):
        return t
    words = [w for w in re.split(r"[\s_\-]+", t) if w]
    if not words or words[-1] not in _BASE:
        return None
    shade = 0.0
    for w in words[:-1]:
        if w not in _SHADE:
            return None
        shade = _SHADE[w]
    base = _BASE[words[-1]]
    return _mix(base, shade) if shade else base
