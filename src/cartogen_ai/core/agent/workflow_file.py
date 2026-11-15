"""The shareable workflow file (PLAN-048, owner decisions 1 and 4 of PLAN-047): validation only. Pure: no QGIS, no Qt, no file or network access.

A workflow file is DATA: an ordered list of calls to tools on one reviewed list (tool_lists.FILE_TOOLS), with the project's layers replaced by named
roles the person maps at import. This module decides whether a file may be shown to a person and run at all. It never runs anything, and nothing
here can be bypassed by what a file says: the file is judged only against the rules below.

The rules (each has a test in tests/test_workflow_file.py):
  1. size at most MAX_BYTES, valid JSON, an object, format "cartogen-workflow", version 1 (a newer version is refused with a plain message);
  2. at most MAX_STEPS steps; every step names a tool on the list; never a deleting tool, never a tool run_steps itself refuses;
  3. arguments: only keys the tool advertises, `confirmed` anywhere is a refusal (a file that tries to approve itself is suspicious), required keys
     present, value types match the schema, strings at most MAX_STRING characters, nothing that looks like a file path or URL;
  4. `$n.field` / `$prev.field` point at an earlier step; `@role` names a declared role (and only where the tool takes a string);
  5. metadata (name, description, limitations, data sources) is length-limited text, and is never acted on.
A preset's `args` is accepted in place of `arguments` and converted, with a warning. What this does NOT prove: that a tool on the list is harmless for
every argument (the list is reviewed, the arguments are checked, the normal gates run and the person sees each call), or that the result will equal the
author's (that depends on the colleague's data)."""
import hashlib
import json
import re

from . import step_runner, tool_lists

FORMAT = "cartogen-workflow"
VERSION = 1
MAX_BYTES = 256 * 1024
MAX_STEPS = 20
MAX_STRING = 500
MAX_NOTE = 300
MAX_DEPTH = 6
_ROLE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_ROLE_REF = re.compile(r"^@([A-Za-z0-9_]+)$")
_PATHISH = re.compile(r"(^~|^[A-Za-z]:[\\/]|[\\/]|://|^file:|\.\.)")
_TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
}


def schemas_from(tools_schema):
    """{tool name: its parameters schema} from the OpenAI-style list the plugin keeps. Pure."""
    out = {}
    for item in tools_schema:
        fn = item.get("function", {}) if isinstance(item, dict) else {}
        if isinstance(fn.get("name"), str):
            out[fn["name"]] = fn.get("parameters") or {}
    return out


def fingerprint(document):
    """SHA-256 (hex) of the document in a canonical form (sorted keys, no spaces), so two people can check they hold the same workflow. Pure."""
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _looks_like_path(value):
    return bool(_PATHISH.search(value))


def _scan_value(value, where, problems, roles, step_index, expect_string, depth=0):
    """Checks one argument value (and anything nested in it). Appends sentences to `problems`. Pure."""
    if depth > MAX_DEPTH:
        problems.append(f"{where}: nested too deeply.")
        return
    if isinstance(value, str):
        if len(value) > MAX_STRING:
            problems.append(f"{where}: a text of {len(value)} characters (the limit is {MAX_STRING}).")
            return
        ref = step_runner._REF.match(value)
        if ref:
            target = step_index - 1 if ref.group(1) == "prev" else int(ref.group(1))
            if not 1 <= target < step_index:
                problems.append(f"{where}: the reference {value} must point to an EARLIER step.")
            return
        if value.startswith("$"):
            problems.append(f"{where}: {value!r} is not a valid reference (use $2.field or $prev.field).")
            return
        if value.startswith("@"):
            role = _ROLE_REF.match(value)
            if not role or role.group(1) not in roles:
                problems.append(f"{where}: {value} is not a role declared in `roles`.")
            elif not expect_string:
                problems.append(f"{where}: a layer role cannot stand where this tool wants a different kind of value.")
            return
        if _looks_like_path(value):
            problems.append(f"{where}: {value[:60]!r} looks like a file path or web address; shared workflows cannot carry those.")
    elif isinstance(value, dict):
        for key, inner in value.items():
            if key == "confirmed":
                problems.append(f"{where}: contains `confirmed`; a workflow file cannot approve anything.")
            _scan_value(inner, f"{where}.{key}", problems, roles, step_index, True, depth + 1)
    elif isinstance(value, list):
        for n, inner in enumerate(value):
            _scan_value(inner, f"{where}[{n}]", problems, roles, step_index, True, depth + 1)


def _check_type(value, spec):
    """True when `value` fits the schema property `spec`, or when the schema says nothing usable. A reference ($) fits anything: it resolves at run time."""
    if isinstance(value, str) and step_runner._REF.match(value):
        return True
    declared = spec.get("type") if isinstance(spec, dict) else None
    if isinstance(declared, list):
        return any(_TYPE_CHECKS[t](value) for t in declared if t in _TYPE_CHECKS) or not any(t in _TYPE_CHECKS for t in declared)
    if declared in _TYPE_CHECKS:
        if declared == "string" and isinstance(value, str):
            return True
        return _TYPE_CHECKS[declared](value) or (declared == "number" and isinstance(value, int) and not isinstance(value, bool))
    return True


def _check_step(index, step, roles, schemas, operation_of, problems, warnings):
    """Validates one step; returns its normalised form or None. Pure."""
    where = f"Step {index}"
    if not isinstance(step, dict) or not isinstance(step.get("tool"), str):
        problems.append(f"{where}: must be an object with a `tool` name.")
        return None
    tool = step["tool"]
    where = f"Step {index} ({tool})"
    for key in step:
        if key not in ("tool", "arguments", "args", "note"):
            warnings.append(f"{where}: the key `{key}` is ignored.")
    if tool in step_runner.NOT_BATCHABLE:
        problems.append(f"{where}: `{tool}` cannot be used in a workflow.")
        return None
    if tool not in schemas:
        problems.append(f"{where}: `{tool}` is not a tool in this version of the plugin.")
        return None
    deletes = operation_of(tool) == "DELETE"
    if tool not in tool_lists.FILE_TOOLS or deletes:
        problems.append(f"{where}: `{tool}` is not on the list of tools a shared workflow may use"
                        + (" (it deletes or replaces project state)." if deletes else "."))
        return None
    if "arguments" in step and "args" in step:
        problems.append(f"{where}: has both `arguments` and `args`; use `arguments`.")
        return None
    arguments = step.get("arguments", step.get("args", {}))
    if "args" in step and "arguments" not in step:
        warnings.append(f"{where}: `args` (the preset spelling) was converted to `arguments`.")
    if not isinstance(arguments, dict):
        problems.append(f"{where}: `arguments` must be an object.")
        return None
    note = step.get("note")
    if note is not None and (not isinstance(note, str) or len(note) > MAX_NOTE):
        problems.append(f"{where}: `note` must be text of at most {MAX_NOTE} characters.")
        return None
    schema = schemas[tool]
    props = (schema or {}).get("properties", {})
    start = len(problems)
    for key, value in arguments.items():
        if key == "confirmed":
            problems.append(f"{where}: contains `confirmed`; a workflow file cannot approve anything.")
            continue
        if key not in props:
            problems.append(f"{where}: `{key}` is not an argument this tool takes.")
            continue
        spec = props[key]
        if not _check_type(value, spec) and not (isinstance(value, str) and value.startswith("@")):
            problems.append(f"{where}: `{key}` should be of type {spec.get('type')}.")
        _scan_value(value, f"{where}, `{key}`", problems, roles, index, spec.get("type") in (None, "string") or isinstance(spec.get("type"), list))
    missing = [r for r in (schema or {}).get("required", []) if r not in arguments]
    if missing:
        problems.append(f"{where}: missing required argument(s): {', '.join(missing)}.")
    if len(problems) > start:
        return None
    out = {"tool": tool, "arguments": arguments}
    if note:
        out["note"] = note
    return out


def _text_list(value, where, limit_items, problems):
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > limit_items or not all(isinstance(v, str) and len(v) <= MAX_STRING for v in value):
        problems.append(f"{where}: must be a list of at most {limit_items} texts of at most {MAX_STRING} characters.")
        return []
    return list(value)


def _load(source):
    """(data, error sentence). Parses text or bytes, or passes a parsed object through. Pure."""
    if isinstance(source, (bytes, str)):
        size = len(source if isinstance(source, bytes) else source.encode("utf-8", "replace"))
        if size > MAX_BYTES:
            return None, f"The file is {size:,} bytes; the limit is {MAX_BYTES:,}."
        try:
            source = json.loads(source)
        except (ValueError, UnicodeDecodeError) as e:
            return None, f"The file is not valid JSON ({type(e).__name__})."
    if not isinstance(source, dict):
        return None, "The file must be a JSON object."
    if source.get("format") != FORMAT:
        return None, f'This is not a Cartogen workflow file (its "format" must be "{FORMAT}").'
    version = source.get("version")
    if not isinstance(version, int) or isinstance(version, bool):
        return None, "The file has no whole-number `version`."
    if version > VERSION:
        return None, f"This file is version {version}; this plugin reads version {VERSION}. Update the plugin to open it."
    if version < 1:
        return None, f"Unknown version {version}."
    return source, None


def _check_header(data, problems, warnings):
    """Name, description, author, created_with and unknown keys. Pure."""
    name = data.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 200:
        problems.append("`name` is required: text of at most 200 characters.")
    description = data.get("description", "")
    if not isinstance(description, str) or len(description) > 2000:
        problems.append("`description` must be text of at most 2,000 characters.")
    for key in ("author", "created_with"):
        if data.get(key) is not None and (not isinstance(data[key], str) or len(data[key]) > 200):
            problems.append(f"`{key}` must be text of at most 200 characters.")
    warnings.extend(f"The key `{key}` is ignored." for key in data
                    if key not in ("format", "version", "name", "description", "author", "created_with", "roles", "steps", "limitations", "data_sources"))


def _check_roles(raw_roles, problems):
    """{role: normalised spec} for the valid roles; problems for the others. Pure."""
    roles = {}
    if not isinstance(raw_roles, dict):
        problems.append("`roles` must be an object.")
        return roles
    for role, raw in raw_roles.items():
        if not _ROLE.match(role):
            problems.append(f"The role name {role!r} must be lower-case letters, digits and underscores, starting with a letter.")
            continue
        spec = raw if isinstance(raw, dict) else {}
        kind, geometry, fields = spec.get("kind", "vector"), spec.get("geometry"), spec.get("fields", [])
        if kind not in ("vector", "raster") or (geometry is not None and geometry not in ("point", "line", "polygon")):
            problems.append(f"Role {role}: `kind` must be vector or raster and `geometry` point, line or polygon.")
            continue
        if not isinstance(fields, list) or not all(isinstance(f, str) and len(f) <= 100 for f in fields) or len(fields) > 30:
            problems.append(f"Role {role}: `fields` must be a list of at most 30 field names.")
            continue
        about = spec.get("about", "")
        roles[role] = {"kind": kind, **({"geometry": geometry} if geometry else {}), **({"fields": fields} if fields else {}),
                       **({"about": about[:MAX_NOTE]} if isinstance(about, str) and about else {})}
    return roles


def _check_steps(raw_steps, roles, schemas, operation_of, problems, warnings):
    """The normalised steps (only those that passed). Pure."""
    if not isinstance(raw_steps, list) or not raw_steps:
        problems.append("`steps` must be a non-empty list.")
        return []
    if len(raw_steps) > MAX_STEPS:
        problems.append(f"At most {MAX_STEPS} steps per file (this one has {len(raw_steps)}).")
        return []
    checked = (_check_step(index, step, roles, schemas, operation_of, problems, warnings) for index, step in enumerate(raw_steps, 1))
    return [step for step in checked if step is not None]


def _check_sources(raw_sources, problems):
    """The cleaned data-source entries (name, url, licence as short text). Pure."""
    if raw_sources is None:
        return []
    if not isinstance(raw_sources, list) or len(raw_sources) > 20 or not all(isinstance(s, dict) for s in raw_sources):
        problems.append("`data_sources` must be a list of at most 20 objects.")
        return []
    sources = []
    for entry in raw_sources:
        clean = {k: entry[k] for k in ("name", "url", "licence") if isinstance(entry.get(k), str) and len(entry[k]) <= 300}
        if clean.get("url") and not clean["url"].lower().startswith(("http://", "https://")):
            problems.append(f"A data source address must start with http:// or https:// (got {clean['url'][:40]!r}).")
        sources.append(clean)
    return sources


def validate(source, schemas, operation_of):
    """(document, problems, warnings). `source` is the file's text/bytes or an already-parsed object; `schemas` maps tool name -> parameters schema
    (schemas_from); `operation_of(name)` gives READ/CREATE/MODIFY/DELETE/PUBLISH. `document` is the normalised workflow (with `fingerprint`) when there
    are no problems, else None. Every problem is one plain sentence naming the step. Pure; never raises on bad input."""
    data, error = _load(source)
    if error:
        return None, [error], []
    problems, warnings = [], []
    _check_header(data, problems, warnings)
    roles = _check_roles(data.get("roles", {}), problems)
    steps = _check_steps(data.get("steps"), roles, schemas, operation_of, problems, warnings)
    used = {m.group(1) for s in steps for m in _role_refs(s["arguments"])}
    if not problems:
        warnings.extend(f"The role `{role}` is declared but no step uses it." for role in roles if role not in used)
    limitations = _text_list(data.get("limitations"), "`limitations`", 20, problems)
    sources = _check_sources(data.get("data_sources"), problems)
    if problems:
        return None, problems, warnings
    document = {"format": FORMAT, "version": VERSION, "name": data["name"].strip(), "description": data.get("description", ""), "roles": roles,
                "steps": steps}
    document.update({key: data[key] for key in ("author", "created_with") if data.get(key)})
    if limitations:
        document["limitations"] = limitations
    if sources:
        document["data_sources"] = sources
    document["fingerprint"] = fingerprint({k: v for k, v in document.items() if k != "fingerprint"})
    return document, [], warnings


def _role_refs(value, depth=0):
    """Every @role reference inside an arguments value. Pure."""
    if depth > MAX_DEPTH:
        return
    if isinstance(value, str):
        m = _ROLE_REF.match(value)
        if m:
            yield m
    elif isinstance(value, dict):
        for inner in value.values():
            yield from _role_refs(inner, depth + 1)
    elif isinstance(value, list):
        for inner in value:
            yield from _role_refs(inner, depth + 1)


def describe_steps(document, operation_of):
    """What the import dialog lists, one entry per step: its number, tool, the kind of change and the arguments as they will be sent (roles still
    shown as @role). Pure."""
    out = []
    for n, step in enumerate(document.get("steps", []), 1):
        out.append({"n": n, "tool": step["tool"], "operation": operation_of(step["tool"]), "note": step.get("note", ""),
                    "arguments": json.dumps(step["arguments"], ensure_ascii=False, sort_keys=True)})
    return out
