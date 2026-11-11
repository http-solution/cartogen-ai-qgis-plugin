"""Refuse to geocode place text that comes from a protected layer (tracker item 1.26; owner decision 2026-11-11: refuse).

Why: geocode_batch and geocode_and_enrich send the place or address text to the public OpenStreetMap Nominatim server. The egress gate (models/egress_gate.py) guards what goes to a cloud AI provider, not what a data-source tool sends
to its own service, and the geocoding tools take bare text, not a layer name, so the gate could not see where the text came from. A layer tagged SENSITIVE or RESTRICTED (for example case addresses in a health project) could be geocoded
against a public server with no question.

What it does, in two independent checks (either one refuses):
  1. the caller names `source_layer` and that layer is protected (its own tag, or inherited through lineage; an untagged layer counts as protected only when the egress gate is in strict mode, as everywhere else);
  2. any of the texts is, after trimming and ignoring case, a value in a text field of a protected layer in the project. The second check does not depend on the caller telling the truth about where the text came from.
It applies whatever the AI provider is, because the text goes to the geocoder either way. It never changes a tag. When it cannot read a protected layer to compare, it refuses and says so (fail closed).

Limits, stated plainly: a text the user retyped or changed (a street without its house number, another spelling, a value split across fields) does not match, so check 2 catches copies of a protected value, not every derived text; a layer
that has no tag and no protected ancestor is open under the default (non-strict) setting. At most MAX_FEATURES features and MAX_VALUES text values per protected layer are compared; a larger layer is refused as 'could not verify'."""
from ...models import egress_gate
from ..protection import effective_sensitivity

MAX_FEATURES = 50_000
MAX_VALUES = 200_000
STATUS = "GEOCODING_REFUSED_PROTECTED"


def norm(text):
    """The form two texts are compared in: trimmed, inner whitespace collapsed, case ignored. Pure."""
    return " ".join(str(text or "").split()).casefold()


def texts_matching(texts, candidates):
    """{layer name: number of the texts found among that layer's values}, only layers with at least one match. candidates is {layer name: set of already normalised values}. Pure."""
    wanted = {norm(t) for t in texts if norm(t)}
    out = {}
    for name, values in candidates.items():
        hit = len(wanted & values)
        if hit:
            out[name] = hit
    return out


def refusal(tool_name, reasons):
    """The result handed to the model. reasons is {layer name: why}. Pure."""
    listed = "; ".join(f"'{n}' ({why})" for n, why in sorted(reasons.items()))
    return {
        "error": f"{tool_name} refused: the place text comes from a protected layer ({listed}), and geocoding sends it to a public server (OpenStreetMap Nominatim).",
        "status": STATUS,
        "tool_name": tool_name,
        "layers": sorted(reasons),
        "message": (
            f"Refused before any lookup: {tool_name} would send text taken from a protected layer ({listed}) to a public geocoding server. Do not retry with different arguments to get around this. "
            "Tell the user plainly why, and that the places can be geocoded from a layer that is tagged PUBLIC or INTERNAL (for example an aggregated or released copy), or with the user's own decision to change the "
            "layer's tag in the Sensitivity dialog."
        ),
    }


def _text_field_indexes(layer):
    from qgis.PyQt.QtCore import QVariant
    string_type = getattr(QVariant, "String", 10)
    return [i for i, f in enumerate(layer.fields()) if f.type() == string_type]


def _protected_layers(all_layers):
    """[(layer, level)] for every layer that is protected now: its own tag, else the lineage-inherited one, with the egress gate's strictness for untagged layers."""
    strict = egress_gate.read_strict()
    out = []
    for layer in all_layers:
        record = effective_sensitivity(layer, all_layers)
        if egress_gate.is_protected(record.get("level"), strict):
            out.append((layer, record.get("level") or "untagged, strict mode"))
    return out


def check(tool_name, texts, source_layer=None):
    """None when the lookup may go ahead, else the refusal dict. Needs QGIS; without it (offline tests of other things) it returns None, because there is then no project to hold a protected layer."""
    try:
        from qgis.core import QgsProject, QgsVectorLayer
    except ImportError:
        return None
    texts = [t for t in (texts or []) if isinstance(t, str)]
    all_layers = list(QgsProject.instance().mapLayers().values())
    protected = _protected_layers(all_layers)
    reasons = {}
    if source_layer:
        named = QgsProject.instance().mapLayersByName(str(source_layer))
        if not named:
            return {"error": f"{tool_name}: source_layer '{source_layer}' is not a layer in this project. Give the layer the place text came from, or leave source_layer out if the user typed the text."}
        for layer, level in protected:
            if layer in named:
                reasons[layer.name()] = f"named as the source, {level}"
    candidates = {}
    for layer, level in protected:
        if not isinstance(layer, QgsVectorLayer) or layer.name() in reasons:
            continue
        try:
            if layer.featureCount() > MAX_FEATURES:
                reasons[layer.name()] = f"{level}; too large to compare ({layer.featureCount():,} features), so it could not be verified"
                continue
            indexes = _text_field_indexes(layer)
            values = set()
            for feature in layer.getFeatures():
                attrs = feature.attributes()
                for i in indexes:
                    v = norm(attrs[i])
                    if v:
                        values.add(v)
                if len(values) > MAX_VALUES:
                    raise ValueError("too many distinct text values")
            candidates[layer.name()] = values
        except Exception:
            reasons[layer.name()] = f"{level}; could not be read to compare, so it could not be verified"
    for name, count in texts_matching(texts, candidates).items():
        level = next((lv for ly, lv in protected if ly.name() == name), "protected")
        reasons[name] = f"{level}; {count} of the {len(texts)} text(s) match values in it"
    return refusal(tool_name, reasons) if reasons else None
