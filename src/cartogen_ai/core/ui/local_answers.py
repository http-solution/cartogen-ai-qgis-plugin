# -*- coding: utf-8 -*-
"""Requests the plugin can answer from the open project alone, with no model call.

Why: a plain "List the layers" went to the model provider and, in the 2026-10-10 hand test, took 13 API calls (the user's count),
each resending the whole system prompt. The answer is a deterministic read of the project, so asking a model adds cost, latency and
a copy of the layer names at the provider for nothing. This module is Qt-free and QGIS-free (it formats the summary that
agent/map_context.get_map_context_summary() already builds) so it is unit-testable without QGIS.

Deliberately narrow: only a request that is nothing but "list / show / what are (the) (loaded) layers (in the project)". Anything
with an extra clause ("list the layers and buffer the roads") goes to the model as before."""
import re

_LIST_LAYERS = re.compile(
    r"^\s*(?:please\s+)?(?:(?:can|could)\s+you\s+)?"
    r"(?:list|show|display|give\s+me|tell\s+me)(?:\s+me)?\s+(?:all\s+)?(?:of\s+)?(?:the\s+|my\s+|our\s+)?(?:loaded\s+|open\s+|current\s+)?"
    r"layers(?:\s+(?:in|of|loaded\s+in)\s+(?:the\s+|this\s+|my\s+)?(?:current\s+)?(?:project|map|canvas|qgis))?\s*[.?!]*\s*$"
    r"|^\s*what\s+layers(?:\s+are)?(?:\s+(?:there|loaded|open))?(?:\s+in\s+(?:the\s+|this\s+|my\s+)?(?:project|map))?\s*[.?!]*\s*$"
    r"|^\s*(?:what\s+are\s+)?(?:the\s+)?(?:loaded\s+)?layers\s*[.?!]*\s*$",
    re.IGNORECASE)

LOCAL_FOOTER = "_Answered from your open project. No model was called._"


def is_list_layers_request(text):
    """True when `text` is only a request to list the project's layers. Pure."""
    return bool(text) and len(str(text)) <= 80 and bool(_LIST_LAYERS.match(str(text)))


def format_layer_list(summary):
    """Markdown answer from a map-context summary dict (see agent/map_context.py). Pure."""
    if not summary or not summary.get("layers"):
        return "There are no layers in the project.\n\n" + LOCAL_FOOTER
    layers = summary["layers"]
    total = summary.get("layer_count", len(layers))
    lines = [f"## {total} layer{'s' if total != 1 else ''} in **{summary.get('project_title', 'the project')}**",
             f"Project CRS **{summary.get('canvas_crs') or 'unknown'}**; active layer **{summary.get('active_layer', 'None')}**.", "",
             "| Layer | Type | CRS | Features | Fields |", "|---|---|---|---|---|"]
    for layer in layers:
        fields = "(withheld: protected layer)" if layer.get("schema_hidden") else ", ".join(layer.get("fields") or []) or "-"
        count = layer.get("feature_count")
        lines.append(f"| `{layer.get('name', '?')}` | {layer.get('type', '?')} | {layer.get('crs') or '-'} | "
                     f"{'-' if count is None else count} | {fields} |")
    if summary.get("truncated"):
        lines += ["", f"_Only the first {len(layers)} of {total} layers are listed._"]
    lines += ["", LOCAL_FOOTER]
    return "\n".join(lines)
