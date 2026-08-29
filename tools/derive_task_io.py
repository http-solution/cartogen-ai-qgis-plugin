# -*- coding: utf-8 -*-
"""Derive the derived fields of the task register, in place.

Adds two keys to every entry of src/cartogen_ai/core/agent/task_register.json:

    "acc"   media kinds a user could usefully ATTACH to this task
            (subset of agent/file_io.MEDIA keys)
    "prod"  file extensions the task should leave behind

and corrects one class of slot mis-assignment (see _STATISTICAL_DISTRIBUTION).

Run:  python tools/derive_task_io.py            # rewrite the register
      python tools/derive_task_io.py --check    # exit 1 if it would change

Why a script and not a one-off edit: 791 tasks is far past the point where a
hand-written table can be trusted or reviewed. Every value in the register is
reproducible from this file, and tests/test_file_io.py re-runs the derivation
and asserts the committed register still matches -- so the two cannot drift,
and any rule change here shows up as a diff rather than as a silent
inconsistency.

The rules are keyword rules over the task text, and they are heuristics -- but
each one is anchored to a tool that genuinely exists to handle that media kind
(see agent/file_io.READERS), so a task never advertises an input the plugin
cannot read.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from cartogen_ai.core.agent import file_io  # noqa: E402

REGISTER = os.path.join(ROOT, "src", "cartogen_ai", "core", "agent", "task_register.json")

# ---------------------------------------------------------------- rules ----

# A documentary source: something whose content arrives as prose or as a table
# inside a document. PDF and DOCX go through extract_pdf_tables /
# extract_word_tables; TXT is read straight into the message.
_DOC = re.compile(r"""
    report|sitrep|situation\s|assessment|survey|questionnaire|form\b|minutes|
    guideline|guidance|protocol|sop\b|policy|plan\b|strategy|appeal|proposal|
    bulletin|brief|note\b|register|roster|contact\s+list|directory|
    terms\s+of\s+reference|checklist|matrix|narrative|log\b|record
""", re.I | re.X)

# Per-unit figures: things that arrive as rows and columns.
_TABLE = re.compile(r"""
    3w\b|4w\b|who\s+does\s+what|operational\s+presence|
    population|census|demograph|caseload|beneficiar|indicator|statistic|
    funding|budget|financial|price|market|stock|pipeline|commodit|
    attendance|enrol|admission|vaccination|coverage\s+rate|
    count\b|tally|figures|dataset|table|spreadsheet|csv|
    incident|casualt|fatalit|displac|arrival|return\b|refugee|idp\b
""", re.I | re.X)

# Pictures: imagery the user has, or a paper map they scanned.
_IMAGE = re.compile(r"""
    imagery|satellite|sentinel|landsat|drone|uav|aerial|orthomosaic|
    photo|picture|scan(?:ned)?|remote\s+sensing|ndvi|ndwi|ndre|
    change\s+detection|damage|rooftop|building\s+footprint|
    land\s+cover|classif|paper\s+map|sketch
""", re.I | re.X)

# The task's own tool chain saying it reads a file off disk.
_PATH_TOOLS = {
    "add_layer_from_path":   ("vector", "raster"),
    "load_3w_data":          ("table",),
    "calculate_presence_gap": ("table",),
    "georeference_image":    ("image",),
    "extract_features_from_imagery": ("image",),
    "load_project":          ("project",),
    "load_tabular_data_as_layer": ("table",),
}

_SCAN = re.compile(r"scan|digiti[sz]e|paper\s+map|historical\s+map|document", re.I)

ORDER = ["pdf", "docx", "txt", "table", "image", "vector", "raster", "project"]


def derive_acc(entry):
    """Media kinds a user could usefully attach to this task."""
    text = "%s %s" % (entry["text"], entry["cname"])
    kinds = set()

    if _DOC.search(text):
        kinds.update(("pdf", "docx"))
    if _TABLE.search(text):
        kinds.add("table")
    if _IMAGE.search(text):
        kinds.add("image")

    for t in entry.get("tools", []):
        for k in _PATH_TOOLS.get(t, ()):
            kinds.add(k)

    # A task that takes a spreadsheet can equally take the same figures out of
    # a PDF or a Word table -- that is exactly what extract_pdf_tables and
    # extract_word_tables exist for. Say so rather than making the user
    # convert the file first.
    if "table" in kinds:
        kinds.update(("pdf", "docx"))

    # A scan or a digitisation job arrives as a PDF at least as often as it
    # arrives as a picture -- extract_pdf_tables reads the tables, and the
    # page image is what the user actually wants georeferenced either way.
    if "image" in kinds and _SCAN.search(text):
        kinds.update(("pdf", "docx"))

    # PDF, DOCX and TXT are one family from the user's side: the same sitrep
    # arrives as any of the three, and all three end up as text in the message
    # (ui/attachments.read_attached_file handles the plain-text fallback for
    # each). Accepting two of them and not the third would be an artefact of
    # the rules, not a real limitation.
    if kinds & {"pdf", "docx"}:
        kinds.update(("pdf", "docx", "txt"))

    if entry["out"] == "guidance":
        # Guidance tasks produce a written procedure. They can be informed by a
        # document, but there is nothing for them to do with a layer file.
        kinds -= {"vector", "raster", "project"}
    else:
        # Every task that ends in a map, a number, a layout or an export can
        # start from a spatial file the user already has -- add_layer_from_path
        # reads all of these, whether or not this particular task's suggested
        # chain happens to name it. Withholding that would be a rules artefact,
        # not a capability limit.
        kinds.update(("vector", "raster"))

    return [k for k in ORDER if k in kinds]


# "population distribution", "age and sex distribution", "teacher
# distribution" are statistical distributions. The slot vocabulary matched them
# on the bare word `distribution` -- which in this register also means a
# distribution point, a real facility type -- and so these tasks were stopping
# to ask the user "which facility or service type?" before mapping population.
# That is not a harmless extra question: it is the plugin asking something
# unanswerable, and the user has no way to know the right reply is "none".
# A distribution POINT is still a facility, and "Monitor distribution
# locations" keeps its slot; only the statistical sense is corrected.
_STATISTICAL_DISTRIBUTION = re.compile(r"""
    \b(population|age|sex|gender|demographic|disease[-\s]vector|health[-\s]worker|
    teacher|staff|worker|personnel|species|rainfall|precipitation|temperature|
    income|wealth|poverty|vegetation|density|size|spatial)\s+
    (?:and\s+\w+\s+)?distribution
""", re.I | re.X)


def derive_slots(entry):
    """The entry's slots with known mis-assignments removed."""
    slots = list(entry.get("slots", []))
    if "facility_type" in slots and _STATISTICAL_DISTRIBUTION.search(entry["text"]):
        slots.remove("facility_type")
    return slots


def derive_prod(entry):
    return file_io.artifacts_for(entry["out"], entry.get("tools", []))


def derive(entries):
    out = []
    for e in entries:
        n = dict(e)
        n["slots"] = derive_slots(e)
        n["acc"] = derive_acc(e)
        n["prod"] = derive_prod(e)
        out.append(n)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the committed register differs from the derivation")
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args()

    with open(REGISTER, encoding="utf-8") as fh:
        data = json.load(fh)
    new = derive(data)

    if args.stats:
        import collections
        acc = collections.Counter()
        prod = collections.Counter()
        none_acc = 0
        for e in new:
            if not e["acc"]:
                none_acc += 1
            for k in e["acc"]:
                acc[k] += 1
            prod[tuple(e["prod"])] += 1
        print("tasks: %d   with no attachable input: %d" % (len(new), none_acc))
        print("accepts:", dict(acc))
        for k, v in prod.most_common():
            print("  produces %-22s %d" % (",".join(k) or "(none)", v))
        return 0

    if args.check:
        if data == new:
            print("register file-io fields are up to date (%d tasks)" % len(new))
            return 0
        diff = [e["id"] for old, e in zip(data, new) if old != e]
        print("register is STALE -- %d task(s) differ, e.g. %s" % (len(diff), diff[:10]))
        return 1

    with open(REGISTER, "w", encoding="utf-8") as fh:
        json.dump(new, fh, ensure_ascii=False, separators=(",", ":"))
    print("rewrote %s (%d tasks)" % (REGISTER, len(new)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
