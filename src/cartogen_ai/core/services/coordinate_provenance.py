"""Where did a point's coordinates come from? (the "invented points" gap noted for 1.16.0, follow-up to #75 / rule 42)

The output router and `find_incident_reports` stop the model filling an empty layer with invented records, but a model can still type
coordinates into a point-creating tool or a script. A fully invented Beirut incident map (the case behind rule 42) is exactly that.
This module checks, after the fact and in code, whether each coordinate the model passed appears anywhere in what the user wrote or
in a tool result this conversation. It never blocks and never decides a point is wrong: a position typed from nowhere is flagged so
the reply can say it is unverified, because the model cannot be trusted to say so itself.

Pure Python, no QGIS import. Limits (said in the note too): a number that happens to match some unrelated figure in the evidence
counts as grounded; a value rounded by more than the tolerance counts as unverified; the script check only sees literal numbers in
`QgsPointXY(x, y)`-style calls, not coordinates computed or read from a file inside the script.
"""
import re

TOOLS = ("add_point_layer", "add_incident_point", "execute_pyqgis_script")
MARKER = "Unverified point positions"
_TOLERANCE = 0.005                      # about 500 m of latitude; a rounded "15.35" still matches 15.3512
_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")
_POINT_CALL = re.compile(r"Qgs(?:PointXY|Point)\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)")
_MAX_EVIDENCE_NUMBERS = 20000


def points_from_call(tool, args):
    """[(first, second, label)] numeric coordinate pairs the model typed into this call; [] when none can be read. Pure."""
    if not isinstance(args, dict):
        return []
    if tool == "add_incident_point":
        return _pair(args.get("lon"), args.get("lat"), str(args.get("description", ""))[:40])
    if tool == "add_point_layer":
        found = []
        for p in args.get("points") or []:
            if not isinstance(p, dict):
                continue
            label = str(p.get("name", ""))[:40]
            if p.get("lon") is not None or p.get("lat") is not None:
                found += _pair(p.get("lon"), p.get("lat"), label)
            else:
                found += _pair(p.get("x"), p.get("y"), label)
        return found
    if tool == "execute_pyqgis_script":
        code = str(args.get("code") or args.get("script") or "")
        return [(float(a), float(b), "script") for a, b in _POINT_CALL.findall(code)]
    return []


def _pair(a, b, label):
    try:
        return [(float(a), float(b), label)]
    except (TypeError, ValueError):
        return []


def evidence_numbers(text):
    """Absolute values of every number in `text`, as a list (bounded). Pure."""
    out = []
    for m in _NUMBER.finditer(str(text or "")):
        try:
            out.append(abs(float(m.group(0))))
        except ValueError:
            continue
        if len(out) >= _MAX_EVIDENCE_NUMBERS:
            break
    return out


def _grounded(value, numbers):
    v = abs(value)
    return any(abs(v - n) <= _TOLERANCE for n in numbers)


def unverified_points(points, evidence):
    """The subset of `points` where either coordinate appears nowhere in `evidence` (within a small tolerance). Pure."""
    numbers = evidence_numbers(evidence)
    return [p for p in points if not (_grounded(p[0], numbers) and _grounded(p[1], numbers))]


def result_note(total, unverified):
    """The sentence added to the tool result the model reads, or None when every point is grounded. Pure."""
    if not unverified:
        return None
    return (f"{len(unverified)} of {total} point position(s) were typed by the model: neither coordinate pair appears in the user's "
            "message or in any tool result this conversation. Tell the user plainly that these positions are unverified and "
            "where they would need to come from (their own data, a geocoder or a source feed); do not describe them as located "
            "or confirmed, and do not add more points the same way.")


def final_note(count):
    """The footnote appended to the final reply when `count` unverified positions were created this turn. Pure."""
    return (f"\u2139\ufe0f **{MARKER}:** {count} point position(s) created in this turn were supplied by the model, not by your data, a "
            "geocoder or a source feed. Treat their locations as unverified until you check them.")


def apply_final_note(final_text, count):
    """`final_text` with the footnote appended once, or unchanged when nothing was flagged. Pure."""
    if not final_text or not count or MARKER in str(final_text):
        return final_text
    return f"{str(final_text).rstrip()}\n\n{final_note(count)}"


def check_call(tool, args, result, evidence):
    """(total points, unverified points) for a call that succeeded; (0, []) for a failed or unrelated call. Pure."""
    if tool not in TOOLS or (isinstance(result, dict) and "error" in result):
        return 0, []
    points = points_from_call(tool, args)
    return len(points), unverified_points(points, evidence)
