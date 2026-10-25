"""Find a print layout by the name a person would type, not only by its exact name.

rc45 smoke run, check I6: the layout is called "Layout_Test_Layout" (made from the request "Test Layout"); asked to draw into "Test Layout" the tool
answered "layout not found", and the elevation-profile chain stopped. Three layout modules each called `layoutByName(name)` (exact match). The
resolver below tries the exact name first, then ignores case, spaces, underscores and a leading "Layout", and only answers when exactly one
layout fits, so a loose name never picks the wrong layout. Pure; QGIS objects are only asked for .name().
"""


def layout_name_for(title):
    """The name a new layout gets: the title as the person gave it (extra spaces collapsed). It used to be "Layout_" plus the title with underscores, so
    "create a print layout called Big Map" produced "Layout_Big_Map" (1.18.0 hand run, row A12). `lookup`/`resolve_layout` still find a layout by
    either spelling, so older projects and requests that use the prefixed name keep working. Pure."""
    name = " ".join(str(title or "").split())
    return name or "Layout"


def _key(name):
    text = "".join(ch for ch in str(name or "").lower() if ch.isalnum())
    return text[len("layout"):] if text.startswith("layout") and len(text) > len("layout") else text


def resolve_layout(layouts, name):
    """The layout in `layouts` that `name` means, or None when none or more than one fit. `layouts`: objects with .name()."""
    items = list(layouts)
    for layout in items:
        if layout.name() == name:
            return layout
    wanted = _key(name)
    if not wanted:
        return None
    close = [layout for layout in items if _key(layout.name()) == wanted]
    return close[0] if len(close) == 1 else None


def lookup(manager, name):
    """The layout `name` means in a QgsLayoutManager: the exact name first, then resolve_layout over its print layouts. The manager is passed in
    (not fetched here) so each calling module keeps using its own QgsProject."""
    exact = manager.layoutByName(name)
    if exact is not None:
        return exact
    try:
        return resolve_layout(manager.printLayouts(), name)
    except TypeError:
        return None
