"""Build a shareable workflow file from what the plugin recorded (PLAN-048 stage 2). Pure: no QGIS, no file access.

Input is the same recorded history the workflow report reads (workflow_report.gather: per layer, the tools that made it, their arguments, their input
layers, and the data sources behind it). Output is a document that workflow_file.validate accepts, or the reasons it could not be built.

What it does to the recorded arguments, so that a file carries no one's project or machine:
  * keeps only the keys the tool advertises, and never `confirmed`;
  * a layer the chain did not make itself (one the person loaded, or whose origin is unknown) becomes a ROLE: every argument value equal to its name
    becomes "@role", and the person who opens the file maps the role to one of their own layers. A layer the chain DID make keeps its name, because
    the exported steps make it again under that name;
  * a step is left out, with the reason, when its tool is not on the list a file may use, or when validation refuses it (for example an argument
    that looks like a file path). Later steps are NOT rewritten to hide a gap: if an included step needs a layer that a left-out step made, that
    layer becomes a role, and the person is told.
It never writes layer contents. A layer's name, geometry type and field NAMES appear in the roles (the person sees them in the preview first).
What it cannot do: tell whether a left-out step mattered to the result, or whether the steps will give the same numbers on another machine."""
import json
import re

from . import tool_lists, workflow_file, workflow_report

_ROLE_CHARS = re.compile(r"[^a-z0-9_]+")


def _role_name(layer_name, taken):
    """A valid, unused role name made from a layer name. Pure."""
    base = _ROLE_CHARS.sub("_", layer_name.lower()).strip("_")[:36] or "layer"
    if not base[0].isalpha():
        base = "layer_" + base
    name, n = base, 2
    while name in taken:
        name, n = f"{base}_{n}", n + 1
    return name


def _calls(entries):
    """Every recorded call once, oldest first: [{tool, params, inputs, outputs, at}]. A call that made two layers is recorded on both; here it is one
    call. Pure."""
    merged = {}
    for entry in entries:
        for h in entry["history"]:
            key = (h.get("timestamp") or "", h.get("tool"), json.dumps(h.get("params"), sort_keys=True, default=str))
            call = merged.setdefault(key, {"tool": h.get("tool"), "params": h.get("params") or {}, "inputs": [], "outputs": [], "at": key[0]})
            call["outputs"].append(entry["layer"])
            call["inputs"].extend(s for s in h.get("sources") or [] if isinstance(s, str) and s not in call["inputs"])
    return sorted(merged.values(), key=lambda c: c["at"])


def _rewrite(value, mapping, depth=0):
    """`value` with every string equal to a mapped layer name replaced by its "@role". Pure."""
    if depth > workflow_file.MAX_DEPTH:
        return value
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, dict):
        return {k: _rewrite(v, mapping, depth + 1) for k, v in value.items() if k != "confirmed"}
    if isinstance(value, list):
        return [_rewrite(v, mapping, depth + 1) for v in value]
    return value


def _mentions(value, names, depth=0):
    """Layer names that appear INSIDE a longer string in `value` (not replaced; the person is warned). Pure."""
    found = []
    if depth > workflow_file.MAX_DEPTH:
        return found
    if isinstance(value, str):
        found.extend(n for n in names if n != value and n in value)
    elif isinstance(value, dict):
        for v in value.values():
            found.extend(_mentions(v, names, depth + 1))
    elif isinstance(value, list):
        for v in value:
            found.extend(_mentions(v, names, depth + 1))
    return found


def _data_sources(entries):
    out = []
    for entry in entries:
        for record in entry.get("sources", []):
            clean = {k: record[k] for k in ("name", "url", "licence") if isinstance(record.get(k), str) and record[k]}
            if clean and clean not in out:
                out.append(clean)
    return out[:20]


def build(entries, schemas, operation_of, name, description="", layer_info=None):
    """{"document", "problems", "skipped", "warnings", "roles"}. `entries` come from workflow_report.gather; `layer_info(layer_name)` may return
    {"kind", "geometry", "fields"} for a loaded layer. `document` is None when nothing could be exported (`problems` says why). Pure."""
    problems, warnings, skipped = [], [], []
    calls = _calls(entries)
    usable = []
    for call in calls:
        tool = call["tool"]
        if tool not in tool_lists.FILE_TOOLS or tool not in schemas:
            skipped.append({"tool": tool, "outputs": call["outputs"], "why": f"`{tool}` is not on the list of tools a shared workflow may use."})
        else:
            usable.append(call)

    produced = {out for call in usable for out in call["outputs"]}
    needed = [i for call in usable for i in call["inputs"]]
    external = [n for n in dict.fromkeys(needed) if n not in produced]
    # an input produced only by a left-out step is external too: the person must supply it
    roles, mapping = {}, {}
    for layer in external:
        role = _role_name(layer, roles)
        info = (layer_info(layer) if layer_info else None) or {}
        spec = {"kind": info.get("kind", "vector")}
        if info.get("geometry"):
            spec["geometry"] = info["geometry"]
        if info.get("fields"):
            spec["fields"] = list(info["fields"])[:30]
        spec["about"] = f"stands for the layer '{layer}' in the original project"[:workflow_file.MAX_NOTE]
        roles[role] = spec
        mapping[layer] = f"@{role}"

    steps = []
    for call in usable:
        props = (schemas[call["tool"]] or {}).get("properties", {})
        arguments = _rewrite({k: v for k, v in call["params"].items() if k in props and k != "confirmed"}, mapping)
        step = {"tool": call["tool"], "arguments": arguments}
        trial = {"format": workflow_file.FORMAT, "version": workflow_file.VERSION, "name": "x", "roles": roles, "steps": [step]}
        _doc, why, _w = workflow_file.validate(trial, schemas, operation_of)
        if why:
            skipped.append({"tool": call["tool"], "outputs": call["outputs"], "why": why[0].split(": ", 1)[-1]})
            continue
        steps.append(step)
        warnings.extend(f"Step {len(steps)} ({call['tool']}): the layer name '{m}' appears inside a longer text and was left as it is."
                        for m in dict.fromkeys(_mentions(arguments, external)))

    if not steps:
        problems.append("No step of this history can be exported" + (": " + "; ".join(s["why"] for s in skipped[:3]) if skipped else "."))
    elif len(steps) > workflow_file.MAX_STEPS:
        problems.append(f"The history has {len(steps)} exportable steps; a file holds at most {workflow_file.MAX_STEPS}. Name a narrower set of layers.")
    if skipped and steps:
        warnings.append(f"{len(skipped)} recorded step(s) were left out; the file will not reproduce everything that was done.")
    if problems:
        return {"document": None, "problems": problems, "skipped": skipped, "warnings": warnings, "roles": mapping}

    document = {"format": workflow_file.FORMAT, "version": workflow_file.VERSION, "name": name.strip()[:200] or "Exported workflow",
                "description": (description or "")[:2000], "roles": roles, "steps": steps,
                "limitations": ["Exported from the recorded history of one session; the steps have not been run again from this file.",
                                "Layer roles are filled in by the person who opens the file; results depend on their data."]}
    sources = _data_sources(entries)
    if sources:
        document["data_sources"] = sources
    checked, why, _w = workflow_file.validate(document, schemas, operation_of)
    if why:                                           # a bug in this module, not in the history: say so rather than write a bad file
        return {"document": None, "problems": ["The exported file did not pass its own check: " + why[0]], "skipped": skipped,
                "warnings": warnings, "roles": mapping}
    return {"document": document, "fingerprint": checked["fingerprint"], "problems": [], "skipped": skipped, "warnings": warnings, "roles": mapping}


def export_from_layers(layer_names, lookup, schemas, operation_of, name, description="", layer_info=None):
    """gather + build in one call. `lookup(name)` returns a layer or None. Pure given those callables."""
    entries = workflow_report.gather(layer_names, lookup)
    if not any(e["found"] for e in entries):
        return {"document": None, "problems": ["None of the named layers is in the project."], "skipped": [], "warnings": [], "roles": {}}
    return build(entries, schemas, operation_of, name, description, layer_info)

