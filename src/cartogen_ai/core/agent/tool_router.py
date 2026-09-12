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

# Common English function/filler words, excluded from name/description scoring -- 2026-09-12,
# a follow-up to the word-boundary fix above: switching to word-boundary matching correctly
# stopped "hi" from matching inside "histogram_equalization", but a query like "hello there"
# still pulled in the full top_k candidate set, because "there" genuinely appears as a real
# standalone word in several tool descriptions' ordinary English prose ("is there flooding
# here", "there is no addressable map item") -- a true word-boundary match, not a bug, just an
# extremely common word carrying no real intent signal. Deliberately small and conservative --
# only words with essentially zero chance of ever being the actual point of a GIS request, never
# a real (if short) content word like "map" or "fix". Doesn't touch the curated alias list
# (_TOOL_ALIASES) or the always_include/fallback logic below, only the two generic scoring loops.
_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "am",
    "this", "that", "these", "those", "there", "here", "it", "its",
    "and", "or", "but", "to", "of", "in", "on", "at", "for", "with",
    "as", "by", "from", "so", "if", "than", "then",
    "i", "you", "he", "she", "we", "they", "my", "your", "me",
    "hi", "hey", "hello", "thanks", "thank", "please", "ok", "okay", "yes", "no",
}


class ToolRouter:
    """Keyword & intent-based tool schema selector."""

    def __init__(self, full_schema_list: List[Dict]):
        self.full_schema_list = full_schema_list

    def filter_relevant_tools(self, user_query: str, top_k: int = 40) -> List[Dict]:
        """Returns top_k relevant tool schemas matching user query terms."""
        if len(self.full_schema_list) <= top_k:
            return self.full_schema_list

        query_lower = user_query.lower()
        # _STOPWORDS removed here only -- query_lower (used by the separate curated-alias
        # check below) keeps every word, since a multi-word alias phrase like "rank the
        # districts" is matched as a whole substring, not word-by-word.
        query_words = set(re.findall(r'\w+', query_lower)) - _STOPWORDS

        # Always include core agent/task/memory tools. execute_pyqgis_script is
        # handled separately below (point 1 of
        # docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md): unlike these
        # genuinely-always-relevant bookkeeping tools, it's an arbitrary-code
        # last resort that was previously guaranteed a slot on every single
        # query regardless of relevance, undermining its own "rare, clearly-
        # fenced fallback" framing.
        always_include = {
            "get_layers", "get_attributes", "create_plan", "update_task",
            "set_task_preview", "store_project_memory", "store_global_memory",
            "generate_spatial_report"
        }
        _FALLBACK_TOOL = "execute_pyqgis_script"

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

            # Word-boundary matching, not substring containment -- 2026-09-12, from a live
            # token-usage report: a plain "hi" was costing ~8K tokens in wholly irrelevant tool
            # schemas because `"hi" in "histogram_equalization"` (and highlight_features,
            # hillshade) is True as a raw substring check, even though "hi" never appears there
            # as an actual word. Same bug hit longer words too, just less obviously: "there" (5
            # chars, already past the old length guard) still substring-matched inside "whereby"
            # and 6 other tool descriptions. Splitting the tool name on "_" and tokenizing the
            # description with the same \w+ regex used for query_words turns both checks into
            # real word-boundary membership tests instead of "is this text contained anywhere in
            # that text" -- the length guards below are now a secondary noise filter (e.g. "to"),
            # not the only thing standing between a short query word and a false match.
            name_words = set(name.lower().split("_"))
            desc_words = set(re.findall(r"\w+", desc))

            score = 0
            # Name match score
            if query_words & {w for w in name_words if len(w) > 2}:
                score += 10

            # Description match score
            for word in query_words:
                if len(word) > 2 and word in desc_words:
                    score += 2

            # Curated alias/synonym match score
            for alias in _TOOL_ALIASES.get(name, []):
                if alias in query_lower:
                    score += _ALIAS_MATCH_SCORE

            scored_tools.append((score, tool_obj))

        # execute_pyqgis_script scored normally above, like every other
        # non-core tool -- it only gets a guaranteed slot here as a true
        # last resort, when nothing else in the whole candidate set scored
        # any real relevance at all (a query sharing no vocabulary with any
        # registered tool). On a query that matched something real, it
        # competes on its own natural score instead of an unconditional
        # synthetic boost, so genuinely-relevant tools aren't crowded out
        # and the model isn't nudged toward arbitrary code execution by
        # default. Confirmed live-code-execution capability doesn't
        # silently vanish either way: on a real match, several other
        # tools' own descriptions already steer the model back to
        # execute_pyqgis_script if truly needed (see e.g. layout_tools.py/
        # styling_tools.py's "don't hand-write X via execute_pyqgis_script"
        # framing) -- this only changes whether it's guaranteed *visible*,
        # not whether the model can still ask for it by name if it somehow
        # already knows to.
        # Excludes always_include too, not just the fallback tool itself --
        # those are synthetic 1000-scores unrelated to whether this
        # specific query matched anything real, and would otherwise make
        # "nothing else matched" false on every single query (confirmed by
        # this exact bug shipping to a failing test before this fix: a
        # nonsense query with zero real relevance still had get_layers/
        # create_plan/etc.'s synthetic 1000 in `other_scores`).
        other_scores = [
            score for score, tool in scored_tools
            if tool.get("function", {}).get("name") not in always_include | {_FALLBACK_TOOL}
        ]
        nothing_else_matched = not other_scores or max(other_scores) <= 0
        if nothing_else_matched:
            scored_tools = [
                (1000, tool) if tool.get("function", {}).get("name") == _FALLBACK_TOOL else (score, tool)
                for score, tool in scored_tools
            ]

        # Sort by score descending and take top_k
        scored_tools.sort(key=lambda x: x[0], reverse=True)
        if nothing_else_matched:
            # Genuinely no real signal at all (e.g. a plain "hi") -- only the always-relevant
            # core tools + the fallback (9 total) are actually useful; padding out to top_k with
            # random 0-score filler tools (still sorted, just no real relevance) was pure waste,
            # found from a live report: it was costing ~8K tokens in irrelevant tool schemas for
            # a one-word greeting. A query WITH any real signal is completely unaffected by this
            # -- it still gets the full top_k candidate pool exactly as before.
            return [tool for score, tool in scored_tools if score > 0][:top_k]
        return [tool for _, tool in scored_tools[:top_k]]
