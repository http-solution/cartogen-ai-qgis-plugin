# -*- coding: utf-8 -*-
"""The Humanitarian Mapping Task Register, as machine-readable task contracts.

792 tasks across 36 sections. Each entry carries:

    id      "07.14"          section number . position, stable
    cat     "7"              section number
    cname   "Health and ..." section name
    text    "Map disease-vector distribution"
    out     "layer"          output contract, see OUTPUTS
    slots   ["aoi", ...]     information the task cannot proceed without
    tools   [...]            suggested tool chain, ALL validated against the
                             live registry -- acquisition first, renderer last
    kw      [...]            matching vocabulary

The data lives in task_register.json beside this module rather than inline:
it is ~218 KB, and the plugin must not pay that cost on every import. It is
loaded lazily on first use and cached.

Why matching happens here and not in the model: the full register is roughly
40 KB of prose. services/prompt_refiner.py deliberately keeps its system message
under ~500 characters. Sending the register -- once, let alone per call --
is not affordable, so a query is matched locally and only the ONE matched
task's contract is injected.
"""
import json
import os

OUTPUTS = ("layer", "layout", "dashboard", "report", "analysis", "dataset", "guidance")

# What each output contract means for the response the user should end up with.
OUTPUT_INTENT = {
    "layer":     "one or more styled QGIS layers on the canvas",
    "layout":    "a composed print layout ready to export",
    "dashboard": "an HTML dashboard",
    "report":    "a written report with supporting figures",
    "analysis":  "numeric results, a table, and a short interpretation",
    "dataset":   "an exported dataset or schema, not a rendered map",
    "guidance":  "written guidance or a procedure -- no GIS output expected",
}

# Human-readable prompts for each slot, used when asking the user.
SLOT_QUESTIONS = {
    "aoi":            "Which area? (a loaded layer, a place name, or the current canvas extent)",
    "admin_level":    "Which administrative level? (admin0 country / admin1 / admin2 / admin3)",
    "time_range":     "Which period, or which two dates to compare?",
    "hazard_type":    "Which hazard specifically?",
    "imagery":        "Which imagery source or date range should be used?",
    "population_src": "Which population source? (WorldPop, an HDX dataset, or a layer you already have)",
    "facility_type":  "Which facility or service type?",
    "threshold":      "What distance or travel-time threshold?",
    "sector":         "Which sector?",
    "dem_source":     "Which DEM should be used? Include resolution and vertical datum if known.",
    "idf_source":     "Which authoritative local IDF curve or rainfall station should supply the design intensity?",
    "runoff_coefficient": "What locally justified Rational Method runoff coefficient C should be used?",
}

# Defaults applied when the user does not answer. Per the 'ask once, then
# default' policy these MUST be stated back to the user, never applied silently.
SLOT_DEFAULTS = {
    "aoi":            ("current canvas extent", "canvas"),
    "admin_level":    ("admin2", "static"),
    "time_range":     ("most recent available data", "static"),
    "hazard_type":    (None, "ask"),          # too consequential to guess
    "imagery":        ("most recent low-cloud scene", "static"),
    "population_src": ("WorldPop", "static"),
    "facility_type":  (None, "ask"),
    "threshold":      ("5 km", "static"),
    "sector":         (None, "ask"),
    "dem_source":     (None, "ask"),          # never guessed: see task_matcher's note on the engineering slots
    "idf_source":     (None, "ask"),
    "runoff_coefficient": (None, "ask"),
}

_DATA = None
_BY_ID = None


def _data_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "task_register.json")


def load():
    """Return the register as a list of dicts. Cached; safe to call often.

    Degrades to an empty register rather than raising -- a missing or corrupt
    data file must not stop the plugin loading.
    """
    global _DATA, _BY_ID
    if _DATA is not None:
        return _DATA
    try:
        with open(_data_path(), encoding="utf-8") as fh:
            _DATA = json.load(fh)
    except Exception as e:  # pragma: no cover - diagnostic path
        print("[TaskRegister] could not load task_register.json: %s" % e)
        _DATA = []
    _BY_ID = {e["id"]: e for e in _DATA}
    return _DATA


def by_id(task_id):
    load()
    return (_BY_ID or {}).get(task_id)


def categories():
    """[(number, name, task_count)] in register order."""
    seen, out = set(), []
    for e in load():
        if e["cat"] not in seen:
            seen.add(e["cat"])
            out.append((e["cat"], e["cname"], sum(1 for x in _DATA if x["cat"] == e["cat"])))
    return out


def stats():
    d = load()
    counts = {}
    for e in d:
        counts[e["out"]] = counts.get(e["out"], 0) + 1
    return {"tasks": len(d), "categories": len(categories()), "outputs": counts}
