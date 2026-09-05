# -*- coding: utf-8 -*-
"""What kinds of FILE a task can take in, and what kinds of file it puts out.

The task register (task_register.py) models abstract slots -- area of interest,
admin level, hazard type. That is only half of what a request needs. The other
half is concrete: the user drops a situation-report PDF, a photo of a damaged
bridge, a 3W spreadsheet, or a plain-text list of village names into the chat,
and expects the plugin to know what to do with it -- and expects the answer
back as the right kind of artifact, not as chat prose.

This module is the file-type half. Two things live here:

1.  MEDIA -- the media kinds the plugin can actually ingest, each defined by
    its extensions and each with a REAL registered tool behind it. Nothing is
    listed here aspirationally: every reader named in READERS is asserted to
    exist in the live TOOL_REGISTRY by tests/test_file_io.py, so this table
    cannot claim a capability the plugin does not have.

2.  ARTIFACTS -- what each output contract is expected to leave on disk, with
    the tool that writes it. Same rule: every writer is checked against the
    registry.

Deliberately Qt-free and QGIS-free, like task_matcher.py, so all of it is unit
testable outside QGIS.
"""
import os

# --------------------------------------------------------------- media -----

# kind -> extensions. Order matters only for `describe`; membership is what is
# used. '.tif' appears under both image and raster on purpose -- a GeoTIFF is a
# raster, a plain TIFF scan is a picture, and only the file itself can say
# which. classify() resolves that ambiguity in favour of raster, because the
# plugin's raster path handles a plain TIFF correctly while the image path
# would discard the georeferencing of a real GeoTIFF.
MEDIA = {
    "image":   (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"),
    "pdf":     (".pdf",),
    "txt":     (".txt", ".md", ".rst", ".log"),
    "docx":    (".docx",),
    "table":   (".csv", ".xlsx", ".xls", ".tsv"),
    "vector":  (".shp", ".geojson", ".json", ".gpkg", ".kml", ".kmz", ".gml"),
    "raster":  (".tif", ".tiff", ".img", ".vrt", ".jp2", ".asc"),
    "project": (".qgz", ".qgs"),
}

# The three the user is most likely to attach by hand, named explicitly because
# the whole point of this module is that a picture, a PDF and a text file each
# take a different route into the same answer.
DOCUMENT_KINDS = ("pdf", "docx", "txt")

# kind -> the registered tool that turns a file of that kind into something the
# agent can reason over. Asserted against TOOL_REGISTRY in tests.
READERS = {
    "pdf":     "extract_pdf_tables",
    "docx":    "extract_word_tables",
    "table":   "load_tabular_data_as_layer",
    "vector":  "add_layer_from_path",
    "raster":  "add_layer_from_path",
    "image":   "georeference_image",
    "project": "load_project",
    # txt has no reader tool by design: plain text is read straight into the
    # message by ui/attachments.read_attached_file and needs no tool call.
    "txt":     None,
}

# What each reader actually gives back, in one line, for the prompt preview.
READER_EFFECT = {
    "pdf":     "tables extracted from the PDF (falling back to its text)",
    "docx":    "tables extracted from the Word document",
    "table":   "the spreadsheet loaded as a layer or aggregated table",
    "vector":  "the vector file added to the project as a layer",
    "raster":  "the raster added to the project as a layer",
    "image":   "the picture, georeferenced if control points are given, "
               "otherwise read visually",
    "project": "the QGIS project opened",
    "txt":     "the text read directly into the request",
}

# Alternative readers worth naming when the task itself says what the file is
# for. Keyed by (kind, keyword-in-task-text).
SPECIALISED_READERS = {
    ("table", "3w"):          "load_3w_data",
    ("table", "4w"):          "load_3w_data",
    ("table", "presence"):    "load_3w_data",
    ("image", "damage"):      "extract_features_from_imagery",
    ("image", "building"):    "extract_features_from_imagery",
    ("image", "imagery"):     "extract_features_from_imagery",
    ("image", "satellite"):   "extract_features_from_imagery",
    ("image", "drone"):       "extract_features_from_imagery",
}


def classify(path):
    """Media kind for a path, or None when the extension is not one we handle.

    '.tif' resolves to raster, not image -- see MEDIA's comment.
    """
    ext = os.path.splitext(path or "")[1].lower()
    if not ext:
        return None
    for kind in ("raster", "vector", "project", "table", "pdf", "docx", "txt", "image"):
        if ext in MEDIA[kind]:
            return kind
    return None


def reader_for(kind, task_text=""):
    """The tool that should ingest a file of this kind for this task."""
    text = (task_text or "").lower()
    for (k, word), tool in SPECIALISED_READERS.items():
        if k == kind and word in text:
            return tool
    return READERS.get(kind)


def describe_attachment(path, task_text=""):
    """One line the user (and the model) can read: what this file is and what
    will be done with it. Returns None for a file we cannot place."""
    kind = classify(path)
    if kind is None:
        return None
    tool = reader_for(kind, task_text)
    effect = READER_EFFECT.get(kind, "read")
    name = os.path.basename(path)
    if tool:
        return "%s (%s) -> %s via %s" % (name, kind, effect, tool)
    return "%s (%s) -> %s" % (name, kind, effect)


# ------------------------------------------------------------ artifacts ----

# output contract -> (extensions written, tool that writes them). The tools are
# the same ones task_matcher.output_contract() puts in `render`; keeping the
# pairing here means the extension and the writer can never drift apart.
ARTIFACTS = {
    "layout":    ((".pdf", ".png"), "print_map"),
    "dashboard": ((".html",),       "generate_html_dashboard"),
    "report":    ((".md",),         "generate_spatial_report"),
    "analysis":  ((".csv",),        "export_to_csv"),
    "dataset":   ((".gpkg", ".csv"), "export_layer"),
    "layer":     ((),               None),   # lives on the canvas, not on disk
    "guidance":  ((),               None),   # written answer, no file
}

# Charts are an add-on rather than a contract of their own: a report, an
# analysis or a map gains a PNG when the task's own tool chain asks for one.
CHART_TOOLS = ("generate_chart", "generate_sector_coverage_report")

# ...except for guidance, whose contract is "a written procedure, no GIS
# output". A handful of guidance tasks carry generate_chart in their suggested
# chain, which is a mis-assignment in the chain rather than a promise of a
# file; honouring it would have the plugin tell the user to expect a PNG from
# "Support local ownership of geographic data".
_NO_ARTIFACTS = ("guidance",)


def artifacts_for(kind, tools=()):
    """Extensions this contract should leave behind, given the task's tools."""
    exts, _writer = ARTIFACTS.get(kind, ((), None))
    out = list(exts)
    if kind in _NO_ARTIFACTS:
        return out
    if any(t in CHART_TOOLS for t in (tools or ())) and ".png" not in out:
        out.append(".png")
    return out


def writer_for(kind):
    return ARTIFACTS.get(kind, ((), None))[1]


def artifact_sentence(kind, tools=()):
    """Plain-English statement of the file the user will end up with."""
    exts = artifacts_for(kind, tools)
    if not exts:
        if kind == "layer":
            return "styled layers on the QGIS canvas (no file written)"
        return "a written answer in the chat (no file written)"
    listed = ", ".join(e.lstrip(".").upper() for e in exts)
    if len(exts) != 1:
        return "%s files" % listed
    article = "an" if listed[0] in "AEFHILMNORSX" else "a"
    return "%s %s file" % (article, listed)
