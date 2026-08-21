# -*- coding: utf-8 -*-
"""
Semantic Tool Router & Retrieval Engine for Cartogen AI.
Filters top-k relevant tool schemas based on user query keywords and intent matching
to prevent LLM system prompt context overload.
"""

import random
import re
from typing import List, Dict


# Curated phrase synonyms for tools whose real-world paraphrases don't share
# vocabulary with their name/description -- e.g. "rank the districts by how
# bad the situation is" shares no words with calculate_severity_index's name,
# and only a weak substring hit ("rank"/"ranked") with its description, so it
# scored too low to make the top_k candidate set in measured testing against
# realistic (not the tool's own vocabulary) query phrasing. Kept out of the
# tool descriptions themselves (which are sent to the model on every call
# where the tool is selected) since these are routing-only signals, not
# information the model needs once the tool is actually a candidate.
_TOOL_ALIASES = {
    "calculate_severity_index": [
        "worst", "priority", "rank the districts", "how bad", "most affected",
        "needs index", "prioritize",
    ],
    "calculate_presence_gap": [
        "underserved", "understaffed", "under-resourced", "who's helping",
        "who is helping", "operational gap", "coverage gap",
    ],
    "load_3w_data": [
        "who else is working", "who is working", "3w", "4w",
        "operational presence", "who's active", "who's responding",
        "who is active", "who is responding", "which organizations are present",
        "which organisations are present",
    ],
    "generate_html_dashboard": [
        "interactive map", "send to donors", "share with", "web map",
        "donor briefing", "for stakeholders",
    ],
    "analyze_incident_trend": [
        "getting worse", "getting more dangerous", "more dangerous", "worsening",
        "improving", "increasing risk", "escalating", "on the rise",
    ],
    "score_route_incident_risk": [
        "risky", "dangerous route", "safe route", "route safety", "safe to travel",
        "safe to drive",
    ],
    "calculate_ndvi": [
        "vegetation", "vegetation health", "how green", "greenness", "crop health",
        "plant health", "vegetation index",
    ],
    "calculate_ndwi": [
        "surface water", "how much water", "water extent", "is there flooding",
        "flood mapping", "water index",
    ],
    "calculate_ndre": [
        "chlorophyll", "nitrogen stress", "crop nitrogen", "precision agriculture",
        "precision ag",
    ],
    "calculate_raster_change_detection": [
        "before and after", "compare images", "what changed", "how much damage",
        "damage from before to after", "satellite comparison",
    ],
    "population_access_gap": [
        "cash assistance", "voucher assistance", "cash and voucher", "cva feasib",
        "cva viable",
    ],
    "apply_raster_stretch": [
        "raster looks washed out", "raster looks flat", "fix the raster colors",
        "raster color ramp", "raster contrast", "stretch the raster",
        "raster looks grey", "raster looks gray", "colorize the raster",
    ],
}
# Score contribution for an alias phrase match -- comparable to a name match
# (10), since these are curated synonyms for a specific known gap rather than
# an incidental substring hit, but not higher (a real name/description match
# should still win a tie against an alias match).
_ALIAS_MATCH_SCORE = 10


class ToolRouter:
    """Keyword & intent-based tool schema selector."""

    def __init__(self, full_schema_list: List[Dict]):
        self.full_schema_list = full_schema_list

    def filter_relevant_tools(self, user_query: str, top_k: int = 40) -> List[Dict]:
        """Returns top_k relevant tool schemas matching user query terms."""
        if len(self.full_schema_list) <= top_k:
            return self.full_schema_list

        query_lower = user_query.lower()
        query_words = set(re.findall(r'\w+', query_lower))

        # Always include core agent/task/memory tools
        always_include = {
            "get_layers", "get_attributes", "create_plan", "update_task",
            "set_task_preview", "store_project_memory", "store_global_memory",
            "execute_pyqgis_script", "generate_spatial_report"
        }

        # Shuffled so ties (most commonly many tools scoring 0) break
        # differently on every call instead of Python's stable sort always
        # favoring whichever tools happen to be registered earliest across
        # agent/tools/*.py -- that was a silent, consistent bias toward the
        # same tools on every query that didn't score enough real matches,
        # not an actual relevance signal. This doesn't fix a query that
        # genuinely needs a specific low/no-score tool (see the alias list
        # above for that), it just stops the filler slots from being
        # systematically unfair.
        shuffled = list(self.full_schema_list)
        random.shuffle(shuffled)

        scored_tools = []
        for tool_obj in shuffled:
            fn = tool_obj.get("function", {})
            name = fn.get("name", "")
            desc = fn.get("description", "").lower()

            if name in always_include:
                scored_tools.append((1000, tool_obj))
                continue

            score = 0
            # Name match score
            if any(w in name.lower() for w in query_words):
                score += 10

            # Description match score
            for word in query_words:
                if len(word) > 2 and word in desc:
                    score += 2

            # Curated alias/synonym match score
            for alias in _TOOL_ALIASES.get(name, []):
                if alias in query_lower:
                    score += _ALIAS_MATCH_SCORE

            scored_tools.append((score, tool_obj))

        # Sort by score descending and take top_k
        scored_tools.sort(key=lambda x: x[0], reverse=True)
        return [tool for _, tool in scored_tools[:top_k]]
