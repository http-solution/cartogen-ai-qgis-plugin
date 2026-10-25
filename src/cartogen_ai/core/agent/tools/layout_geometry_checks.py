"""PLAN-014 phase 1: geometry problems of a print layout, found from the layout's own item rectangles.

The QA checklist only asked "is the id there" (title, legend, scale bar, north arrow). It could not see a label whose text is taller than its box,
two items drawn on top of each other, or an item hanging off the page: BUG-2026-09-11-1 (body text running into the footer) was found by a person
looking at a picture. The rules here are pure rectangle tests; the QGIS half reads the rectangles from a real layout.

Deliberate overlaps are not problems: the locator map sits inside the main map (INSET_MAP over MAP_MAIN) and a map's own overview does too.
Everything is reported as a plain sentence; nothing here blocks an export."""
# pairs of item ids that are meant to overlap (order does not matter)
ALLOWED_OVERLAPS = (("MAP_MAIN", "INSET_MAP"),)
OVERLAP_TOLERANCE_MM = 0.5          # frames and rounding: touching edges are not an overlap
OVERFLOW_TOLERANCE_MM = 0.8         # the text-height estimate is deliberately generous; only clear overflow is reported
PAGE_TOLERANCE_MM = 0.5


def rects_overlap(a, b, tolerance=OVERLAP_TOLERANCE_MM):
    """True when rectangles (x, y, width, height) overlap by more than `tolerance` mm in both directions. Pure."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return min(ax + aw, bx + bw) - max(ax, bx) > tolerance and min(ay + ah, by + bh) - max(ay, by) > tolerance


def overlap_problems(items, allowed=ALLOWED_OVERLAPS):
    """['LEGEND overlaps BODY_TEXT', ...] for item pairs that overlap and are not an allowed pair. items: {id: (x, y, w, h)}. Pure."""
    allowed_pairs = {frozenset(pair) for pair in allowed}
    ids = sorted(items)
    out = []
    for i, first in enumerate(ids):
        for second in ids[i + 1:]:
            if frozenset((first, second)) in allowed_pairs:
                continue
            if rects_overlap(items[first], items[second]):
                out.append(f"{first} overlaps {second}")
    return out


def off_page_problems(items, page_size, tolerance=PAGE_TOLERANCE_MM):
    """['TITLE extends past the right edge of the page', ...] for items outside page_size = (width, height). Pure."""
    width, height = page_size
    out = []
    for item_id in sorted(items):
        x, y, w, h = items[item_id]
        for edge, over in (("left", -x), ("top", -y), ("right", x + w - width), ("bottom", y + h - height)):
            if over > tolerance:
                out.append(f"{item_id} extends {over:.0f} mm past the {edge} edge of the page")
    return out


def overflow_problems(labels, tolerance=OVERFLOW_TOLERANCE_MM):
    """['FOOTER text needs 14 mm but the box is 8 mm tall', ...]. labels: {id: (needed_mm, box_mm)}. Pure."""
    return [f"{item_id} text needs about {needed:.0f} mm but its box is {box:.0f} mm tall"
            for item_id, (needed, box) in sorted(labels.items()) if needed - box > tolerance]


def all_problems(items, page_size, labels):
    """overlap + off-page + overflow problems in one list (the order a reader wants: placement first, then text). Pure."""
    return off_page_problems(items, page_size) + overlap_problems(items) + overflow_problems(labels)


try:
    from qgis.core import QgsLayoutItemLabel
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def layout_geometry_problems(layout):
    """all_problems() for a real layout (in mm). Never raises: a check that cannot run is skipped, the export result stays as it was."""
    if not QGIS_AVAILABLE:
        return []
    try:
        from .layout_style import FOOTER_FIT_SLACK_MM, TYPE_SCALE, body_text_height_mm, footer_needed_mm
        page = layout.pageCollection().page(0).pageSize()
        items, labels = {}, {}
        for item in layout.items():
            item_id = item.id() if hasattr(item, "id") else ""
            if not item_id:
                continue
            items[item_id] = (item.x(), item.y(), item.rect().width(), item.rect().height())
            if isinstance(item, QgsLayoutItemLabel) and item.text():
                size = item.textFormat().size() if hasattr(item, "textFormat") else TYPE_SCALE["panel"]
                # the footer box was sized by footer_needed_mm, so it is judged by the same measure; the generous body estimate called every box 1 mm short
                if item_id == "FOOTER":
                    needed = footer_needed_mm(item) - FOOTER_FIT_SLACK_MM    # the same slack the footer growth allows
                else:
                    needed = body_text_height_mm(item.text(), item.rect().width(), size or TYPE_SCALE["panel"], margin_mm=0.5, minimum_mm=1.0)
                labels[item_id] = (needed, item.rect().height())
        return all_problems(items, (page.width(), page.height()), labels)
    except Exception:
        return []
