# -*- coding: utf-8 -*-
"""
Theme-reactive SVG icons for Cartogen AI's dock/chat UI.

Hand-authored, in-repo SVGs (not an icon font, not qtawesome) -- matches the observed QGIS
plugin-ecosystem convention (e.g. opengeos/qgis-plugin-template's icons/ folder) rather than
pulling in a Material/Font Awesome bridge, per the UI/chat redesign workstream's external
research (2026-09-12). Every icon is single-color and takes its color at RENDER time, not asset
-load time -- the same "paint from the live palette" pattern TerraLabAI's QGIS_AI-Segmentation
plugin uses for its own dock icons (palette().color(QPalette.WindowText) as the paint color),
so an icon always matches whatever QGIS theme is actually running instead of being a fixed-color
asset that can go invisible or clash on an unexpected theme.

Deliberately has ZERO qgis.core imports at module level for the path data itself (plain string
constants, testable without QGIS) -- only themed_icon() touches Qt/QGIS, matching this package's
existing split convention (chat_formatting.py is Qt-free for the same reason).
"""

# Each entry is raw SVG body markup (no outer <svg> tag) using {color} as the one substitution
# point for the icon's single color -- kept as an f-string-ready template, not real SVG until
# themed_icon() fills it in, so a caller can render the same glyph in any color without
# re-authoring the path.
_ICON_TEMPLATES = {
    # A paperclip -- two nested hook curves, stroke-only (no fill) so it reads as an outline
    # icon at small sizes, matching the send/stop/settings icons' stroke weight below.
    "attach": (
        '<path d="M15.5 6.5 L8 14a2.5 2.5 0 0 0 3.54 3.54L19 10a4.5 4.5 0 1 0-6.36-6.36L6 10.28" '
        'fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
    ),
    # A right-pointing arrow -- the send action.
    "send": (
        '<path d="M4 12h15M13 6l6 6-6 6" fill="none" stroke="{color}" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
    ),
    # A rounded square -- the stop action, standard media-control convention.
    "stop": (
        '<rect x="6" y="6" width="12" height="12" rx="2.5" fill="{color}"/>'
    ),
    # Three horizontal sliders (line + a filled circle "handle" at a different position on
    # each) -- a settings/preferences glyph that's simple geometry (lines + circles), not a
    # hand-drawn gear, deliberately: a gear is far harder to get looking right by hand at small
    # sizes than this well-established alternative metaphor.
    "settings": (
        '<g fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round">'
        '<line x1="4" y1="7" x2="20" y2="7"/><circle cx="15" cy="7" r="2" fill="{color}" stroke="none"/>'
        '<line x1="4" y1="12" x2="20" y2="12"/><circle cx="9" cy="12" r="2" fill="{color}" stroke="none"/>'
        '<line x1="4" y1="17" x2="20" y2="17"/><circle cx="17" cy="17" r="2" fill="{color}" stroke="none"/>'
        '</g>'
    ),
}


def icon_svg(name, color_hex):
    """Returns a complete, standalone SVG document string (24x24 viewBox) for the named icon in
    the given color. Pure string work, no Qt/QGIS needed -- the half of this module that's
    directly unit-testable."""
    if name not in _ICON_TEMPLATES:
        raise ValueError(f"Unknown icon name: {name!r}. Known icons: {sorted(_ICON_TEMPLATES)}")
    body = _ICON_TEMPLATES[name].format(color=color_hex)
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">{body}</svg>'


def themed_icon(name, color_hex, size=20):
    """Renders the named icon at the given color as a real QIcon, in memory -- no temp file.
    QGIS-dependent (QSvgRenderer/QPainter/QPixmap); call this from UI code, not from anything
    that needs to import without a live QGIS process."""
    from qgis.PyQt.QtCore import QByteArray, Qt
    from qgis.PyQt.QtGui import QIcon, QPainter, QPixmap
    from qgis.PyQt.QtSvg import QSvgRenderer

    svg_bytes = QByteArray(icon_svg(name, color_hex).encode("utf-8"))
    renderer = QSvgRenderer(svg_bytes)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)
