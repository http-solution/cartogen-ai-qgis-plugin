"""PLAN-014 phase 2: A3, A2 and A1 pages for create_print_layout.

create_print_layout lays everything out in millimetres for an A4 page, a geometry with a live-verified history of overlap bugs
(BUG-2026-09-11-1), so that geometry is left exactly as it is. A larger page is made by building the layout at A4 and then scaling the
finished layout by one factor: item positions and sizes, text sizes, margins, frame widths, legend and scale-bar spacing. The map keeps its
geographic extent (a bigger sheet shows the same area larger, not more area). For A4 the factor is 1 and nothing is touched, so an A4 layout
is byte-for-byte what it was before.

The sizes are the A series only (owner decision, 2026-10-24: A4, A3, A2, A1); all four share one aspect ratio, which is why one factor is exact.
The factor and name rules are pure and run without QGIS; the scaling itself needs a real layout and is covered by tests/test_plan014_live.py."""
import contextlib

from .layout_options import PAGE_SIZES

PAGE_SIZE_KEYS = ("a4", "a3", "a2", "a1")


def validate_page_size(size):
    """('a3', None) for a supported page size (case and spaces ignored; empty means A4), else (None, message). Pure."""
    key = str(size or "a4").strip().lower().replace(" ", "")
    if key not in PAGE_SIZE_KEYS:
        return None, f"page_size must be one of: {', '.join(k.upper() for k in PAGE_SIZE_KEYS)} (got '{size}')."
    return key, None


def page_dimensions(size, orientation):
    """(width, height) in mm of an A-series page in the given orientation. Pure."""
    w, h = PAGE_SIZES[size]
    return (h, w) if str(orientation).lower() != "portrait" else (w, h)


def scale_factor(size, orientation):
    """The factor from the A4 page of the same orientation to `size`: the smaller of the width and height ratios, so nothing built for A4 can
    stick out of the bigger page. 1.0 for A4. Pure."""
    base_w, base_h = page_dimensions("a4", orientation)
    w, h = page_dimensions(size, orientation)
    return min(w / base_w, h / base_h)


try:
    from qgis.core import (QgsLayoutItemLabel, QgsLayoutItemLegend, QgsLayoutItemMap, QgsLayoutItemScaleBar, QgsLayoutMeasurement, QgsLayoutPoint,
                           QgsLayoutSize, QgsLegendStyle)
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def _scale_text_format(fmt, k):
    fmt.setSize(fmt.size() * k)
    return fmt


def _scale_item_look(item, k, mm, warnings):
    """Text sizes, margins, frame width and legend / scale-bar spacing of one item, times k. Each step is independent: a missing call on this
    QGIS build leaves that one setting at its A4 value and says so, the layout is still produced."""
    def step(name, fn):
        try:
            fn()
        except Exception as exc:
            warnings.append(f"{item.id()}: could not scale {name} ({type(exc).__name__})")

    if hasattr(item, "frameStrokeWidth") and item.frameEnabled():
        step("frame", lambda: item.setFrameStrokeWidth(QgsLayoutMeasurement(item.frameStrokeWidth().length() * k, mm)))
    if isinstance(item, QgsLayoutItemLabel):
        step("text size", lambda: item.setTextFormat(_scale_text_format(item.textFormat(), k)))
        step("margins", lambda: (item.setMarginX(item.marginX() * k), item.setMarginY(item.marginY() * k)))
    elif isinstance(item, QgsLayoutItemLegend):
        def legend():
            for name in ("Title", "Group", "Subgroup", "SymbolLabel"):
                member = getattr(getattr(QgsLegendStyle, "Style", QgsLegendStyle), name, None)
                if member is not None:
                    style = item.rstyle(member)
                    style.setTextFormat(_scale_text_format(style.textFormat(), k))
            item.setSymbolWidth(item.symbolWidth() * k)
            item.setSymbolHeight(item.symbolHeight() * k)
            item.setBoxSpace(item.boxSpace() * k)
        step("legend text and symbols", legend)
    elif isinstance(item, QgsLayoutItemScaleBar):
        step("scale bar text", lambda: item.setTextFormat(_scale_text_format(item.textFormat(), k)))
        step("scale bar spacing", lambda: (item.setHeight(item.height() * k), item.setBoxContentSpace(item.boxContentSpace() * k),
                                           item.setLabelBarSpace(item.labelBarSpace() * k)))
    elif isinstance(item, QgsLayoutItemMap):
        def grids():
            for grid in item.grids().asList():
                if hasattr(grid, "annotationTextFormat"):
                    grid.setAnnotationTextFormat(_scale_text_format(grid.annotationTextFormat(), k))
        step("graticule text", grids)


def scale_layout(layout, size, orientation, mm):
    """Resizes `layout` (built for A4) to `size` and scales every item; returns a list of warnings (empty when everything scaled).

    `mm` is the layout-millimetre unit enum (layout_tools.LAYOUT_MM). A4 returns [] without touching the layout. Never raises."""
    if not QGIS_AVAILABLE:
        return []
    key, problem = validate_page_size(size)
    if problem:
        return [problem]
    k = scale_factor(key, orientation)
    if abs(k - 1.0) < 1e-9:
        return []
    warnings = []
    try:
        extents = {item.id(): item.extent() for item in layout.items() if isinstance(item, QgsLayoutItemMap) and item.id()}
        width, height = page_dimensions(key, orientation)
        layout.pageCollection().page(0).setPageSize(QgsLayoutSize(width, height, mm))
        for item in layout.items():
            item_id = item.id() if hasattr(item, "id") else ""
            if not item_id:
                continue
            x, y, w, h = item.x(), item.y(), item.rect().width(), item.rect().height()
            with contextlib.suppress(Exception):
                _scale_item_look(item, k, mm, warnings)
            item.attemptMove(QgsLayoutPoint(x * k, y * k, mm))
            item.attemptResize(QgsLayoutSize(w * k, h * k, mm))
        for item_id, extent in extents.items():
            item = layout.itemById(item_id)
            if item is not None:
                item.setExtent(extent)       # the same area, drawn larger: resizing a map item keeps its scale and so changes its extent
    except Exception as exc:
        warnings.append(f"page size {key.upper()} could not be applied ({type(exc).__name__}: {exc}); the layout stays A4")
    return warnings
