# -*- coding: utf-8 -*-
"""
Regenerates docs/TOOLS_REFERENCE.md directly from the live TOOL_REGISTRY/
TOOLS_SCHEMA -- so the tool reference can never drift out of sync with the
actual registered tools the way a hand-maintained list would. Run this after
adding, removing, or changing any @register_tool-decorated function:

    python docs/generate_tools_reference.py

Does not require a running QGIS -- every tools/*.py module degrades to
QGIS_AVAILABLE = False at import time outside QGIS, but @register_tool itself
runs regardless (it just registers the function/schema, doesn't call it).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from cartogen_ai.core.agent.tools import TOOL_REGISTRY, TOOLS_SCHEMA  # noqa: E402
from cartogen_ai.core.agent.agent import NETWORK_ONLY_TOOLS, TWO_PHASE_TOOLS, TASK_MANAGEMENT_TOOLS  # noqa: E402


def _group_key(name):
    module = TOOL_REGISTRY[name].__module__.rsplit(".", 1)[-1]
    labels = {
        "vector_tools": "Vector & Geoprocessing",
        "raster_tools": "Raster",
        "styling_tools": "Styling & Labeling",
        "export_tools": "Export & Reporting",
        "system_tools": "System, Search & Scripting",
        "task_tools": "Task & Memory Management",
        "humanitarian_tools": "Humanitarian Data (HDX / OSM / geoBoundaries)",
        "layout_tools": "Print Layouts",
        "db_and_workflow_tools": "Database & Workflows",
        "multimodal_remote_sensing": "Satellite Imagery & Vision",
        "analysis_tools": "Data Analysis & Prediction",
        "project_tools": "Project Management",
        "reporting_tools": "Reporting & Document Analysis",
        "logistics_tools": "Humanitarian Logistics",
        "imagery_extraction": "AI Imagery Feature Extraction",
        "monitoring_tools": "Monitoring & Scheduling",
    }
    return labels.get(module, module)


def _flag_str(name):
    flags = []
    if name in NETWORK_ONLY_TOOLS:
        flags.append("network-only")
    if name in TWO_PHASE_TOOLS:
        flags.append("two-phase")
    if name in TASK_MANAGEMENT_TOOLS:
        flags.append("task-management")
    return f" _({', '.join(flags)})_" if flags else ""


def generate():
    groups = {}
    for entry in TOOLS_SCHEMA:
        fn = entry["function"]
        name = fn["name"]
        groups.setdefault(_group_key(name), []).append(entry)

    lines = [
        "# Tool Reference",
        "",
        f"Auto-generated from the live tool registry ({len(TOOLS_SCHEMA)} tools) by "
        "`docs/generate_tools_reference.py` -- do not hand-edit, regenerate instead so this "
        "can never drift from the actual code.",
        "",
        "Flags: **network-only** tools bypass the main-thread QGIS dispatcher entirely (pure "
        "HTTP, safe from any background thread); **two-phase** tools split a network fetch "
        "(background thread) from the QGIS-touching part (main thread); **task-management** "
        "tools are excluded from auto-advance in the Task Manager.",
        "",
    ]

    for group in sorted(groups):
        entries = sorted(groups[group], key=lambda e: e["function"]["name"])
        lines.append(f"## {group}")
        lines.append("")
        for entry in entries:
            fn = entry["function"]
            name = fn["name"]
            desc = fn["description"]
            params = fn.get("parameters", {}).get("properties", {})
            required = set(fn.get("parameters", {}).get("required", []))

            lines.append(f"### `{name}`{_flag_str(name)}")
            lines.append("")
            lines.append(desc)
            lines.append("")
            if params:
                lines.append("| Parameter | Type | Required | Description |")
                lines.append("|---|---|---|---|")
                for pname, pschema in params.items():
                    ptype = pschema.get("type", "any")
                    if ptype == "array":
                        item_type = pschema.get("items", {}).get("type", "any")
                        ptype = f"array[{item_type}]"
                    pdesc = pschema.get("description", "")
                    req = "yes" if pname in required else "no"
                    lines.append(f"| `{pname}` | {ptype} | {req} | {pdesc} |")
                lines.append("")
            else:
                lines.append("_No parameters._")
                lines.append("")

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "TOOLS_REFERENCE.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Wrote {out_path} ({len(TOOLS_SCHEMA)} tools across {len(groups)} groups)")


if __name__ == "__main__":
    generate()
