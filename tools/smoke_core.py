"""Pure half of the agent-run smoke runner (no QGIS import, so it is unit-tested offline). tools/run_smoke_headless.py is the QGIS half.

Why this exists: the 2026-11-13/14 full live smoke test was handed to a small chat agent that was told to "collect the evidence" by hand
(screenshots, clicks, typing into the QGIS console). It stopped after two rows, and pasted stale clipboard text into the chat for a third.
Here nothing depends on an agent remembering to save: the runner calls the plugin's tools itself and writes every file, and a row can
only be PASS if at least one machine check ran and every check held. A row whose pass condition needs a person looking at a map is
never marked PASS here; it is listed as NEEDS-EYES so nobody mistakes "no error" for "looks right".
"""
import csv
import hashlib
import json
import math
import os

REQUIRED_ROW_FILES = ("row.json", "checks.txt", "verdict.json")


def get_path(data, path):
    """Dotted lookup in nested dicts/lists ('classes.0'); returns (found, value). Pure."""
    cur = data
    for part in str(path).split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.lstrip("-").isdigit() and -len(cur) <= int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return False, None
    return True, cur


def _approx(a, b, tol):
    try:
        return math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=tol)
    except (TypeError, ValueError):
        return False


def evaluate(check, results, layer_values=None):
    """One check -> (ok, detail). `results` is the list of tool results in step order; `layer_values(layer, field)` returns the list of a
    layer's field values (only needed for layer checks). A check that cannot be evaluated is a FAILURE, never a pass. Pure."""
    op = check.get("op")
    try:
        if "layer" in check:
            if layer_values is None:
                return False, "layer check but no way to read layers"
            values = layer_values(check["layer"], check["field"])
            if op == "absent":                                  # the layer must NOT exist (a refusal made nothing); `field` only has to be a name that would be on it
                return values is None, f"layer '{check['layer']}' " + ("is absent" if values is None else "exists")
            if values is None:
                return False, f"layer '{check['layer']}' or field '{check['field']}' not found"
            tol = check.get("tol", 1e-6)
            want = check.get("value")
            nums = [v for v in values if v is not None]
            if op == "all_approx":
                ok = bool(nums) and len(nums) == len(values) and all(_approx(v, want, tol) for v in nums)
            elif op == "max_approx":
                ok = bool(nums) and _approx(max(float(v) for v in nums), want, tol)
            elif op == "sorted_eq":
                ok = len(nums) == len(want) and all(_approx(a, b, tol) for a, b in zip(sorted(float(v) for v in nums), sorted(want), strict=True))
            elif op == "count_eq":
                ok = len(values) == want
            elif op == "any_empty_count_eq":
                ok = sum(1 for v in values if v in (None, "")) == want
            else:
                return False, f"unknown layer op {op!r}"
            return ok, f"{check['layer']}.{check['field']} {op} {want!r}: got {values[:8]!r}"
        step = check.get("step", "last")
        index = len(results) - 1 if step == "last" else int(step) - 1
        if not 0 <= index < len(results):
            return False, f"no step {step} (only {len(results)} ran)"
        found, got = get_path(results[index], check["path"])
        want = check.get("value")
        if op == "present":
            ok = found
        elif not found:
            return False, f"step {index + 1}: '{check['path']}' not in the result"
        elif op == "eq":
            ok = got == want
        elif op == "approx":
            ok = _approx(got, want, check.get("tol", 1e-6))
        elif op == "contains":
            ok = str(want).lower() in str(got).lower()
        elif op == "true":
            ok = bool(got)
        elif op == "ge":
            ok = float(got) >= float(want)
        elif op == "le":
            ok = float(got) <= float(want)
        else:
            return False, f"unknown op {op!r}"
        return ok, f"step {index + 1} {check['path']} {op} {want!r}: got {got!r}"
    except Exception as e:  # a broken check must read as a failure with a reason, not crash the run
        return False, f"check could not be evaluated: {type(e).__name__}: {e}"


def verdict(outcomes, error=None, needs_eyes=False):
    """PASS only when at least one check ran and all held; ERROR if the row crashed; NO-CHECKS if nothing was checked; NEEDS-EYES when a
    person must still judge the picture (even if every machine check held). Pure."""
    if error:
        return "ERROR"
    if not outcomes:
        return "NO-CHECKS"
    if not all(ok for ok, _ in outcomes):
        return "FAIL"
    return "NEEDS-EYES" if needs_eyes else "PASS"


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_row(out_dir, row, record, outcomes, status, note=""):
    """Writes results/evidence/<row id>/{row.json, checks.txt, verdict.json}. record = steps, results, timings, layers, error. Returns the folder."""
    folder = os.path.join(out_dir, "evidence", row["id"])
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "row.json"), "w", encoding="utf-8") as fh:
        json.dump({"row": row["id"], "title": row.get("title", ""), "covers_row": row.get("covers_row", ""), **record}, fh, indent=1, default=str, ensure_ascii=False)
    with open(os.path.join(folder, "checks.txt"), "w", encoding="utf-8") as fh:
        for (ok, detail), check in zip(outcomes, row.get("checks", []), strict=False):
            fh.write(f"{'OK  ' if ok else 'FAIL'} {check.get('what', '')} | {detail}\n")
        if not outcomes:
            fh.write("no check ran\n")
    with open(os.path.join(folder, "verdict.json"), "w", encoding="utf-8") as fh:
        json.dump({"row": row["id"], "status": status, "checks": len(outcomes), "checks_ok": sum(1 for ok, _ in outcomes if ok), "note": note}, fh, indent=1)
    return folder


def verify_evidence(out_dir, row_ids):
    """Problems found in an output folder: missing row folders or files, a PASS with no checks. Empty list = complete. Pure apart from reads."""
    problems = []
    for rid in row_ids:
        folder = os.path.join(out_dir, "evidence", rid)
        problems.extend(f"{rid}: {name} missing" for name in REQUIRED_ROW_FILES if not os.path.isfile(os.path.join(folder, name)))
        try:
            with open(os.path.join(folder, "verdict.json"), encoding="utf-8") as fh:
                v = json.load(fh)
            if v.get("status") == "PASS" and not v.get("checks"):
                problems.append(f"{rid}: PASS with no checks")
            if v.get("status") == "PASS" and v.get("checks") != v.get("checks_ok"):
                problems.append(f"{rid}: PASS but not every check held")
        except (OSError, ValueError):
            problems.append(f"{rid}: verdict.json unreadable")
    return problems


def write_results(out_dir, rows, statuses):
    """RESULTS.csv (one line per row) and SUMMARY.md. Pure apart from writes."""
    with open(os.path.join(out_dir, "RESULTS.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["row", "covers_row", "status", "evidence_folder"])
        for row in rows:
            w.writerow([row["id"], row.get("covers_row", ""), statuses.get(row["id"], "NOT RUN"), f"evidence/{row['id']}"])
    counts = {}
    for row in rows:
        s = statuses.get(row["id"], "NOT RUN")
        counts[s] = counts.get(s, 0) + 1
    lines = ["# Agent-run smoke: summary\n", ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())) + "\n",
             "PASS means every machine check held. NEEDS-EYES means the checks held and a person must still look at the picture. This run never saves a screenshot.\n"]
    lines += [f"- {row['id']}: {statuses.get(row['id'], 'NOT RUN')}" for row in rows]
    with open(os.path.join(out_dir, "SUMMARY.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
