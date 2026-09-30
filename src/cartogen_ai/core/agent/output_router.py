# -*- coding: utf-8 -*-
"""Make the answer come back in the shape the task promised.

task_matcher.output_contract() says what a request should turn into -- a
styled layer, a print layout, an HTML dashboard, a CSV, a written report.
Saying it is not the same as getting it: a model handed a dashboard task will
quite happily add three layers, describe them, and stop, because from its side
the question has been answered. The user is then told they will get an HTML
file and gets chat prose instead. That gap is what this module closes.

The approach is deliberately not "call the renderer ourselves". The renderers
need arguments -- which layer, which field, which output path -- that only the
model, holding the conversation, knows. Guessing them would produce a
confidently wrong artifact, which in humanitarian work is worse than none.

So instead: after a turn finishes, compare the contract against the tools that
actually ran. If the renderer never ran, send ONE follow-up turn naming
exactly what is still owed. The model has the full context by then and calls
the renderer with real arguments. If it still does not, we stop -- one
follow-up, never a loop.

Everything here is pure: it takes a contract and a list of tool names, and
returns strings and booleans. No QGIS, no Qt, no network -- so all of it is
unit tested for real rather than mocked.
"""

from . import file_io

# A contract with no renderer is satisfied the moment the turn ends: guidance
# is prose, and an analysis contract is satisfied by numeric results in chat/canvas.
_NO_RENDER = ("guidance", "analysis")

# One follow-up per turn. This is the whole loop guard: the caller records that
# a follow-up was issued and passes already_retried=True the second time.
MAX_FOLLOWUPS = 1


def required_renderers(contract):
    """The tools that would satisfy this contract. Any one of them is enough."""
    if not contract:
        return []
    return list(contract.get("render") or [])


def satisfied(contract, executed_tools):
    """True when the turn already produced what the contract promised."""
    if not contract:
        return True
    if contract.get("kind") in _NO_RENDER:
        return True
    needed = required_renderers(contract)
    if not needed:
        return True
    ran = set(executed_tools or [])
    if contract.get("kind") == "layer":
        # A layer contract is met by anything that puts a layer on the canvas,
        # not only by the two styling tools in `render` -- styling an
        # unstyleable layer is not a failure to deliver.
        return any(t.startswith(("add_", "create_", "fetch_", "load_", "geocode_",
                                 "interpolate_", "buffer_", "clip_", "merge_",
                                 "intersect_", "union_", "dissolve_", "spatial_join",
                                 "extract_features_from_imagery", "georeference_image"))
                   or t in needed for t in ran)
    return any(t in ran for t in needed)


def followup_instruction(contract, executed_tools, already_retried=False, has_layers=None):
    """The one extra turn to send, or None when nothing is owed.

    Returns a plain instruction, not a scolding: it names the deliverable, the
    tool that produces it, and the file type the user was promised.
    """
    if already_retried or satisfied(contract, executed_tools):
        return None
    # rc7 smoke test F10: the nudge forced an export_layer call nobody asked for because a task
    # *match* implied a deliverable. Only an output the user named themselves is owed.
    if not contract.get("explicit"):
        return None
    kind = contract.get("kind")
    needed = required_renderers(contract)
    if not needed and kind != "layer":
        return None

    # If the deliverable is a layer and no layer creation tool was executed (or the project has no layers),
    # we must explicitly instruct the agent to CREATE the layer rather than asking it to style a non-existent layer!
    if kind == "layer":
        ran_creator = any(t.startswith(("add_", "create_", "fetch_", "load_", "geocode_",
                                        "interpolate_", "buffer_", "clip_", "merge_",
                                        "intersect_", "union_", "dissolve_", "spatial_join",
                                        "extract_features_from_imagery", "georeference_image"))
                          for t in (executed_tools or []))
        has_canvas_layer = (has_layers is True) or (ran_creator and has_layers is not False)
        if not has_canvas_layer:
            return (
                "The deliverable for this task is a layer on the QGIS canvas, and no layer has been created yet. "
                "Call an appropriate layer creation tool now (such as add_point_layer, add_vector_layer, "
                "geocode_and_enrich, fetch_osm_features, fetch_gdacs_disaster_alerts, or execute_pyqgis_script) "
                "to create and display the requested spatial layer on the canvas. If real-time or live external feeds "
                "are unavailable, generate an operational/representative sample dataset on the canvas with appropriate "
                "attributes and coordinates so the user has the requested spatial layer. Do not answer in prose alone "
                "without creating the layer."
            )

    writer = file_io.writer_for(kind) or (needed[0] if needed else "apply_categorized_style")
    artifact = file_io.artifact_sentence(kind)
    return (
        "The deliverable for this task is %s, and it has not been produced yet. "
        "Using the layers and results already in the project from the previous "
        "step, call %s now to produce it. Do not redo the analysis, and do not "
        "answer in prose instead -- if a required argument is genuinely missing, "
        "say which one and stop." % (artifact, writer)
    )


def delivery_note(contract, executed_tools):
    """One line for the chat log saying what the user actually ended up with.

    Honest in both directions: it says 'not produced' when it was not, rather
    than describing the intended artifact as though it exists.
    """
    if not contract:
        return ""
    kind = contract.get("kind")
    artifact = file_io.artifact_sentence(kind)
    if kind in _NO_RENDER:
        return "Delivered: %s." % artifact
    if satisfied(contract, executed_tools):
        return "Delivered: %s." % artifact
    return ("Expected %s for this task, but the step that writes it did not run."
            % artifact)


def describe_contract(contract):
    """What the user is told BEFORE the call, alongside the prompt preview."""
    if not contract:
        return ""
    kind = contract.get("kind")
    line = "Output: %s -- %s." % (kind, file_io.artifact_sentence(kind))
    if contract.get("overridden"):
        line += " (You asked for this explicitly; it overrides the task default.)"
    return line
