"""Colour maths for the style rules (PLAN-023 R1-7), pure Python, no Qt and no QGIS.

Used by tests/test_style_profiles.py to enforce the L0 rules of docs/PERSONA_TOOLS_STYLING_PLAN_2026-10-04.md section 5: a categorical palette's neighbouring colours must stay apart for people with colour-vision
deficiency (CIEDE2000 >= 10 after simulating deuteranopia, protanopia and tritanopia), and red may not sit beside green. Nothing here draws anything.

Sources, so the numbers can be traced: sRGB -> XYZ (D65) -> CIELAB with the standard matrices; the CIEDE2000 formula of Sharma, Wu and Dalal (2005), checked in the tests against their published test pairs; the colour-vision simulation is
Machado, Oliveira and Fernandes (2009), severity 1.0, applied in linear RGB. A simulation is a model of average dichromatic vision, not a measurement of any one person."""
import math

D65_WHITE = (0.95047, 1.0, 1.08883)

# Machado et al. 2009, severity 1.0 (full dichromacy), applied to linear RGB
CVD_MATRICES = {
    "deuteranopia": ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.011820, 0.042940, 0.968881)),
    "protanopia": ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216), (-0.003882, -0.048116, 1.051998)),
    "tritanopia": ((1.255528, -0.076749, -0.178779), (-0.078411, 0.930809, 0.147602), (0.004733, 0.691367, 0.303900)),
}


def hex_to_rgb(value):
    """'#RRGGBB' or 'RRGGBB' -> (r, g, b) 0..255."""
    text = value.lstrip("#")
    if len(text) != 6:
        raise ValueError(f"not a six-digit hex colour: {value!r}")
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))


def _to_linear(channel):
    c = channel / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _from_linear(c):
    c = min(1.0, max(0.0, c))
    return 255.0 * (12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055)


def rgb_to_lab(rgb):
    r, g, b = (_to_linear(c) for c in rgb)
    x = 0.4124564 * r + 0.3575761 * g + 0.1804375 * b
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = 0.0193339 * r + 0.1191920 * g + 0.9503041 * b

    def f(t):
        return t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116
    fx, fy, fz = f(x / D65_WHITE[0]), f(y / D65_WHITE[1]), f(z / D65_WHITE[2])
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def simulate(rgb, kind):
    """The colour as seen with the given deficiency ('deuteranopia', 'protanopia', 'tritanopia'), as (r, g, b) 0..255 floats."""
    matrix = CVD_MATRICES[kind]
    lin = [_to_linear(c) for c in rgb]
    return tuple(_from_linear(sum(m * v for m, v in zip(row, lin, strict=True))) for row in matrix)


def delta_e2000(lab1, lab2):
    """CIEDE2000 colour difference between two CIELAB colours (Sharma, Wu, Dalal 2005, kL = kC = kH = 1)."""
    l1, a1, b1 = lab1
    l2, a2, b2 = lab2
    c1, c2 = math.hypot(a1, b1), math.hypot(a2, b2)
    c_bar = (c1 + c2) / 2
    g = 0.5 * (1 - math.sqrt(c_bar ** 7 / (c_bar ** 7 + 25 ** 7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)

    def hue(b, a):
        if a == 0 and b == 0:
            return 0.0
        h = math.degrees(math.atan2(b, a))
        return h + 360 if h < 0 else h
    h1p, h2p = hue(b1, a1p), hue(b2, a2p)
    dl = l2 - l1
    dc = c2p - c1p
    if c1p * c2p == 0:
        dh = 0.0
    else:
        diff = h2p - h1p
        dh = diff - 360 if diff > 180 else diff + 360 if diff < -180 else diff
    d_h = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dh / 2))
    l_bar = (l1 + l2) / 2
    cp_bar = (c1p + c2p) / 2
    if c1p * c2p == 0:
        hp_bar = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hp_bar = (h1p + h2p) / 2
    else:
        hp_bar = (h1p + h2p + 360) / 2 if h1p + h2p < 360 else (h1p + h2p - 360) / 2
    t = (1 - 0.17 * math.cos(math.radians(hp_bar - 30)) + 0.24 * math.cos(math.radians(2 * hp_bar))
         + 0.32 * math.cos(math.radians(3 * hp_bar + 6)) - 0.20 * math.cos(math.radians(4 * hp_bar - 63)))
    d_theta = 30 * math.exp(-(((hp_bar - 275) / 25) ** 2))
    rc = 2 * math.sqrt(cp_bar ** 7 / (cp_bar ** 7 + 25 ** 7))
    sl = 1 + 0.015 * (l_bar - 50) ** 2 / math.sqrt(20 + (l_bar - 50) ** 2)
    sc = 1 + 0.045 * cp_bar
    sh = 1 + 0.015 * cp_bar * t
    rt = -math.sin(math.radians(2 * d_theta)) * rc
    return math.sqrt((dl / sl) ** 2 + (dc / sc) ** 2 + (d_h / sh) ** 2 + rt * (dc / sc) * (d_h / sh))


def colour_difference(hex_a, hex_b, kind=None):
    """CIEDE2000 between two '#RRGGBB' colours, optionally as seen with a deficiency in CVD_MATRICES."""
    a, b = hex_to_rgb(hex_a), hex_to_rgb(hex_b)
    if kind:
        a, b = simulate(a, kind), simulate(b, kind)
    return delta_e2000(rgb_to_lab(a), rgb_to_lab(b))


def hue_degrees(hex_colour):
    """HSV hue 0..360, or None for a grey (no hue to speak of)."""
    r, g, b = (c / 255 for c in hex_to_rgb(hex_colour))
    top, low = max(r, g, b), min(r, g, b)
    if top - low < 0.08:
        return None
    if top == r:
        h = ((g - b) / (top - low)) % 6
    elif top == g:
        h = (b - r) / (top - low) + 2
    else:
        h = (r - g) / (top - low) + 4
    return h * 60


def is_red(hex_colour):
    h = hue_degrees(hex_colour)
    return h is not None and (h >= 340 or h <= 20)


def is_green(hex_colour):
    h = hue_degrees(hex_colour)
    return h is not None and 85 <= h <= 165


def red_beside_green(colours):
    """The adjacent pairs (i, i+1) of a palette where one is red and the other green. Empty means the rule holds."""
    return [(i, i + 1) for i in range(len(colours) - 1)
            if (is_red(colours[i]) and is_green(colours[i + 1])) or (is_green(colours[i]) and is_red(colours[i + 1]))]


def weak_neighbours(colours, minimum=10.0):
    """[(i, kind, difference)] for every adjacent pair of a palette whose CIEDE2000 falls below `minimum` in normal vision (kind None) or in any simulated deficiency."""
    problems = []
    for i in range(len(colours) - 1):
        for kind in (None, *CVD_MATRICES):
            d = colour_difference(colours[i], colours[i + 1], kind)
            if d < minimum:
                problems.append((i, kind, round(d, 2)))
    return problems
