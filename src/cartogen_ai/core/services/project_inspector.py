# -*- coding: utf-8 -*-
"""
Deterministic Project Inspector snapshot.

IMPLEMENTATION_TRACKER.md §1.5, option (b), decided by Alaa 2026-09-24: the narrow, isolated
first-stage experiment over the full Intent Interpreter -> Project Inspector -> Spatial Planner
pipeline (option (c)) point 18 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md
describes -- "the most self-contained piece," measured before committing to the rest.

Point 18's proposal names the Project Inspector's scope explicitly: "Layers/CRS/Fields/
Layouts/Themes/Metadata." `agent/map_context.py`'s existing get_map_context_summary() (unconditional,
sent on every turn already) already covers Layers/CRS/Fields -- this module exists ONLY for the
genuine gap: Layouts, Themes, and Metadata, none of which the agent sees today unless it spends a
tool call on list_layouts/list_map_themes/get_layers to find out. Deliberately NOT folded into
map_context.py itself: that function is always-on and unconditional; this one is feature-flagged
(SETTINGS_PROJECT_INSPECTOR_ENABLED, default OFF, same "build it, evaluate later" reasoning as
plan_gate.py's §1.6 sibling) specifically so its effect can be measured in isolation from
map_context's already-shipped, already-proven behavior -- conflating the two would make it
impossible to tell which one any observed effect came from.

Deterministic and synchronous, no LLM call -- exactly the "Project Inspector" stage's own
description: a snapshot step that runs BEFORE planning, not a reasoning step.
"""

MAX_LAYOUTS = 10
MAX_THEMES = 10
MAX_KEYWORD_VOCABULARIES = 5

try:
    from qgis.core import QgsProject
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def inspect_project() -> dict:
    """Returns a capped snapshot of the current project's print layouts, saved map themes,
    and project metadata (title/abstract/author/keywords). Returns {} if QGIS isn't available,
    or if the project has none of the three (nothing new to tell the model beyond what
    map_context.py already sends). Never raises -- mirrors get_map_context_summary()'s own
    try/except-and-return-{} shape."""
    if not QGIS_AVAILABLE:
        return {}

    try:
        project = QgsProject.instance()

        layout_names = [lo.name() for lo in project.layoutManager().layouts()]
        theme_names = list(project.mapThemeCollection().mapThemes())

        md = project.metadata()
        keywords = {}
        try:
            raw_keywords = md.keywords()
            for vocabulary, terms in list(raw_keywords.items())[:MAX_KEYWORD_VOCABULARIES]:
                keywords[vocabulary] = list(terms)
        except Exception:
            keywords = {}

        metadata = {
            "title": md.title() or "",
            "abstract": md.abstract() or "",
            "author": md.author() or "",
            "keywords": keywords,
        }

        if not layout_names and not theme_names and not any(metadata.values()):
            return {}

        return {
            "layouts": layout_names[:MAX_LAYOUTS],
            "layouts_truncated": len(layout_names) > MAX_LAYOUTS,
            "themes": theme_names[:MAX_THEMES],
            "themes_truncated": len(theme_names) > MAX_THEMES,
            "metadata": metadata,
        }
    except Exception as e:
        print(f"[ProjectInspector] Failed to build project inspector snapshot: {e}")
        return {}
