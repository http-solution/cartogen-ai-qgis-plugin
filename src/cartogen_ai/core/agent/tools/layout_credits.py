"""PLAN-014 phase 1: the credit line of a print layout.

Before this, a layout drew an OpenStreetMap (or CARTO, Esri...) basemap and said nothing about where it came from: the legend deliberately
leaves basemaps out (layout_style.legend_layer_ids) and the Sources line covers thematic layers only. data_source_tools.BASEMAPS already holds a
vetted attribution for every basemap the plugin can add and tells the user to "keep the attribution on published maps"; this puts it on the map.

A credit is only ever taken from that table or from a layer's own metadata (rights); a web layer the table does not know says so instead of
getting a guessed credit. Pure, so it runs without QGIS."""
from urllib.parse import unquote, urlparse

from .data_source_tools import BASEMAPS

WEB_PROVIDERS = ("wms", "xyz", "arcgismapserver", "vectortile")
NOT_RECORDED = "credit not recorded"
CREDITS_CHAR_BUDGET = 150


def _prefix(template):
    """Host and path of a tile URL template up to the first placeholder, without the scheme: 'tile.openstreetmap.org/'."""
    parsed = urlparse(template)
    return (parsed.netloc + parsed.path).split("{", 1)[0]


def basemap_credit(source, basemaps=None):
    """(credit text, True) when `source` is a basemap from the vetted table, else (host or '', False). Pure."""
    text = unquote(str(source or ""))
    for spec in (basemaps or BASEMAPS).values():
        prefix = _prefix(spec[0])
        if prefix and prefix in text:
            return spec[3], True
    host = ""
    if "url=" in text:
        host = urlparse(text.split("url=", 1)[1].split("&", 1)[0]).netloc
    return host, False


def credit_entries(layers):
    """['Basemap: OpenStreetMap contributors (ODbL)', ...] for the visible web layers, plus each visible layer's own rights text.

    layers: iterable of dicts {name, provider, source, rights (list of str), visible}. Order of first appearance, each credit once. Pure."""
    seen, out = set(), []
    for layer in layers:
        if not layer.get("visible"):
            continue
        provider = str(layer.get("provider") or "").lower()
        if provider in WEB_PROVIDERS:
            credit, known = basemap_credit(layer.get("source"))
            text = f"Basemap: {credit}" if known else f"Basemap {layer.get('name')}: {NOT_RECORDED}" + (f" ({credit})" if credit else "")
            if text not in seen:
                seen.add(text)
                out.append(text)
        for raw in layer.get("rights") or []:
            right = str(raw).strip()
            text = f"{layer.get('name')}: {right}"
            if right and text not in seen:
                seen.add(text)
                out.append(text)
    return out


def credits_line(entries, budget=CREDITS_CHAR_BUDGET):
    """'Credits: a; b' within `budget` characters; credits that do not fit are counted ('+2 more'), never dropped silently. '' when none. Pure."""
    entries = [e for e in entries if e]
    if not entries:
        return ""
    prefix = "Credits: "
    full = prefix + "; ".join(entries)
    if len(full) <= budget:
        return full
    limit = budget - len(" +99 more")
    kept, used = [], len(prefix)
    for entry in entries:
        add = len(entry) + (2 if kept else 0)
        if kept and used + add > limit:
            break
        kept.append(entry if used + add <= limit else entry[: max(10, limit - used - 1)] + "~")
        used += add
    left = len(entries) - len(kept)
    return prefix + "; ".join(kept) + (f" +{left} more" if left else "")
