"""Verified workflow report (PLAN-045, roadmap step D): one document that says what a result is made from and what was checked, built only from
what the plugin recorded -- never from what the model remembers.

Pure: it takes duck-typed layers (name(), customProperty()) and a `lookup(name) -> layer or None`, so it runs without QGIS. Sections:
  1. Result checks that FAILED (first, so they cannot be missed), then a table of every layer and the checks recorded for it.
  2. Data sources (source_record.py): source, licence, retrieval date, coverage.
  3. Steps, in the order they ran (lineage): tool, parameters, input layers, time. This is the rerun recipe: issue the same calls in the same order
     against the same inputs.
  4. Assumptions and limitations: what the owner of the map said (passed in), plus what this report cannot vouch for, computed from the gaps it found.
What it does NOT claim: that rerunning gives the same numbers (not demonstrated), that licences were read from the services, or that a layer with no
recorded checks is correct. Each gap is listed instead of left out."""
import json
import time

from . import source_record

MAX_DEPTH = 6
_MAX_PARAM_CHARS = 200
CHECKS_PROPERTY_KEY = "cartogen/checks"      # same key as result_gate.CHECKS_PROPERTY_KEY (a test pins it); not imported so this module needs no QGIS
LINEAGE_KEY = "cartogen/lineage"


def _prop(layer, key):
    try:
        raw = layer.customProperty(key, "[]")
        data = json.loads(raw) if isinstance(raw, str) and raw.strip() else []
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _lineage_key():
    try:
        from .lineage import LINEAGE_PROPERTY_KEY
        return LINEAGE_PROPERTY_KEY
    except Exception:
        return LINEAGE_KEY


def gather(layer_names, lookup):
    """Entries for the named layers and every layer they were made from (through lineage `sources`), upstream first. Pure given `lookup`."""
    entries, seen = [], set()

    def visit(name, depth):
        if name in seen or depth > MAX_DEPTH:
            return
        seen.add(name)
        layer = lookup(name)
        if layer is None:
            entries.append({"layer": name, "found": False, "history": [], "checks": [], "sources": []})
            return
        history = [h for h in _prop(layer, _lineage_key()) if isinstance(h, dict)]
        for h in history:
            for upstream in h.get("sources") or []:
                if isinstance(upstream, str):
                    visit(upstream, depth + 1)
        entries.append({"layer": name, "found": True, "history": history, "checks": [r for r in _prop(layer, CHECKS_PROPERTY_KEY) if isinstance(r, dict)],
                        "sources": source_record.collect(layer, lookup)})

    for name in layer_names or []:
        visit(name, 0)
    return entries


def _params_text(params):
    if not isinstance(params, dict) or not params:
        return ""
    parts = []
    for key, value in params.items():
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
        parts.append(f"{key}={text[:_MAX_PARAM_CHARS]}{'...' if len(text) > _MAX_PARAM_CHARS else ''}")
    return ", ".join(parts)


def steps(entries):
    """Every recorded step in time order, once each: [{tool, params, inputs, output, at}]. Pure."""
    found, keys = [], set()
    for entry in entries:
        for h in entry["history"]:
            key = (h.get("timestamp"), h.get("tool"), json.dumps(h.get("params"), sort_keys=True, default=str), entry["layer"])
            if key in keys:
                continue
            keys.add(key)
            found.append({"tool": h.get("tool") or "unknown tool", "params": h.get("params") or {}, "inputs": [s for s in h.get("sources") or [] if isinstance(s, str)],
                          "output": entry["layer"], "at": h.get("timestamp") or ""})
    return sorted(found, key=lambda s: s["at"])


def limitations(entries, given=None):
    """The honest gaps this report found, as sentences. Pure."""
    out = []
    unchecked = [e["layer"] for e in entries if e["found"] and not e["checks"]]
    if unchecked:
        out.append("No automated result checks were recorded for: " + ", ".join(unchecked) + ". That means they were not checked, not that they passed.")
    sampled = sorted({e["layer"] for e in entries for run in e["checks"] if run.get("sampled_of")})
    if sampled:
        out.append("Checks read only the first features of large layers: " + ", ".join(sampled) + ".")
    direct = [e["layer"] for e in entries if e["found"] and not e["history"] and not e["sources"]]
    if direct:
        out.append("Origin unknown (loaded directly, not made or fetched by an agent tool): " + ", ".join(direct) + ".")
    missing = [e["layer"] for e in entries if not e["found"]]
    if missing:
        out.append("Not in the project any more, so nothing could be read for: " + ", ".join(missing) + ".")
    records = [r for e in entries for r in e["sources"]]
    if records:
        out.append("Licences are taken from the plugin's own table and were not checked against the data providers; check them before publishing.")
    out.append("The steps below are what was recorded. Rerunning them was not tested by this report, so the same numbers are expected, not shown.")
    out.extend(g for g in (given or []) if isinstance(g, str) and g.strip())
    return out


def build_markdown(title, entries, assumptions=None, generated_at=None):
    """The report text. Pure."""
    lines = [f"# {title}", "", f"Generated {generated_at or time.strftime('%Y-%m-%d %H:%M:%S')} by Cartogen AI from recorded lineage, sources and checks.", ""]
    failed = [(e["layer"], c, run.get("tool")) for e in entries for run in e["checks"][-1:] for c in run.get("checks", []) if c.get("status") == "fail"]
    lines.append("## Result checks")
    if failed:
        lines += ["**FAILED checks (latest run per layer):**"] + [f"- {layer} ({tool}): {c.get('id')} -- {c.get('detail')}" for layer, c, tool in failed] + [""]
    lines += ["| Layer | Latest checks | Run by |", "|---|---|---|"]
    for e in entries:
        if not e["found"]:
            lines.append(f"| {e['layer']} | layer not found | |")
        elif not e["checks"]:
            lines.append(f"| {e['layer']} | none recorded | |")
        else:
            run = e["checks"][-1]
            cells = ", ".join(f"{c.get('id')}: {c.get('status')}" for c in run.get("checks", [])) or "none"
            lines.append(f"| {e['layer']} | {cells} | {run.get('tool')} at {run.get('at')} |")
    lines += ["", "## Data sources"]
    records = []
    for e in entries:
        records += [r for r in e["sources"] if r not in records]
    lines += [f"- {source_record.describe(r)}" for r in records] or ["- No fetched data recorded in this chain."]
    lines += ["", "## Steps (rerun recipe, in order)"]
    ordered = steps(entries)
    for n, s in enumerate(ordered, 1):
        inputs = f" from {', '.join(s['inputs'])}" if s["inputs"] else ""
        params = f" [{_params_text(s['params'])}]" if s["params"] else ""
        lines.append(f"{n}. {s['at']} -- {s['tool']}{inputs} -> {s['output']}{params}")
    if not ordered:
        lines.append("- No steps recorded.")
    lines += ["", "## Assumptions and limitations"] + [f"- {t}" for t in limitations(entries, assumptions)]
    return "\n".join(lines) + "\n"
