# -*- coding: utf-8 -*-
"""
Semantic Tool Router & Retrieval Engine for Cartogen AI.
Filters top-k relevant tool schemas based on user query keywords and intent matching
to prevent LLM system prompt context overload.
"""

import difflib
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
    # Real live report, 2026-09-16: a "Health facilities beyond one hour's travel <coords>"
    # request -- no place names in the query, no facility layer already in the project --
    # spent its whole tool-call budget on execute_pyqgis_script hunting for a local data file
    # on disk and probing the plugin's own internals, never once calling geocode_and_enrich/
    # geocode_batch, even though an earlier turn with the same underlying task DID use them
    # successfully. Root cause not fully instrumented (which tools were actually in that turn's
    # active_tools isn't logged), but is strongly implicated by the scoring itself: neither
    # tool's own description ("Geocode a SINGLE address/place name into lat/lon...") shares any
    # vocabulary with "health facilities beyond one hour's travel", so with no query text to
    # match on, both tools score at or near 0 against a name query -- an easy loss against ~175
    # other registered tools within a top_k=40 cutoff, especially since "health"/"facilit*" /
    # "travel"/"hour" naturally score highly for several OTHER, unrelated tools instead. These
    # aliases give both geocode tools a fighting chance of being visible on exactly the kind of
    # query that most needs them: naming real-world facilities (hospitals, clinics) with no
    # existing coordinate data to start from.
    "geocode_and_enrich": [
        "hospital", "hospitals", "clinic", "clinics", "health facilit",
        "geocode", "find the location of", "where is",
    ],
    "geocode_batch": [
        "hospital", "hospitals", "clinic", "clinics", "health facilit",
        "geocode", "list of locations", "multiple locations",
    ],
    "ingest_osm_features": [
        "hospital", "hospitals", "clinic", "clinics", "health facilit",
        "health facilities", "doctors", "pharmacy", "osm data",
        "download facilities", "fetch facilities", "osm features",
        "infrastructure", "schools", "road network", "highways",
        "osm", "amenities", "amenity",
    ],
    # Hydrology (see tools/engineering_tools.py). "steam length" is the typo in the request that motivated these tools. No bare
    # "tc" alias: aliases match as substrings of the query, so it would boost these tools on "match", "batch" or "catchment".
    "parse_dms_location": [
        "degrees minutes seconds", "dms coordinate", "watershed outlet",
        "watershed area", "stream length", "steam length", "peak flow",
    ],
    "assess_watershed_hydrology_request": [
        "watershed", "catchment", "drainage basin", "stream length", "steam length",
        "return period", "rainfall intensity", "time of concentration", "peak flow",
    ],
    "calculate_rational_watershed_peak_flow": [
        "watershed", "catchment", "rational method", "return period",
        "rainfall intensity", "time of concentration", "peak flow", "kirpich",
    ],
    # Road barriers (see tools/barrier_tools.py). No bare "bridge" or "closed": they would boost this tool on unrelated queries.
    "apply_network_barriers": [
        "destroyed bridge", "damaged bridge", "blocked road", "road closure", "closed road", "flooded road",
        "checkpoint", "barrier", "impassable", "avoid the", "cut off road",
    ],
    # Anticipatory action (see tools/trigger_tools.py). No bare "forecast" or "trigger": forecast_trend and unrelated queries use them.
    "evaluate_forecast_trigger": [
        "anticipatory action", "forecast-based financing", "forecast based financing", "trigger threshold", "trigger model",
        "trigger protocol", "activation threshold", "lead time", "early action", "pre-arranged financing",
    ],
    # Remote mapping tasks (see tools/task_grid_tools.py). No bare "grid" or "tasks": they appear in unrelated requests.
    "generate_mapping_task_grid": [
        "tasking manager", "mapping task", "task grid", "mapswipe", "remote mapping", "crowd mapping", "mapathon",
        "split the area into", "divide the area into",
    ],
    # Survey sampling (see tools/sampling_tools.py). No bare "sample" or "survey": they appear in unrelated requests.
    "design_sampling_frame": [
        "sampling frame", "sample size", "stratified sample", "sampling design", "household survey", "needs assessment",
        "msna", "enumerator", "margin of error", "cluster sampling", "random sample of households",
    ],
    # Multi-criteria ranking and survey aggregation (see tools/mcda_tools.py, tools/survey_tools.py). No bare "rank", "weights" or "survey".
    "calculate_mcda_ranking": [
        "multi-criteria", "multicriteria", "mcda", "weighted ranking", "rank the districts", "rank districts", "prioritise areas",
        "prioritize areas", "prioritisation", "prioritization", "weight sensitivity", "rank stability",
    ],
    "calculate_allocation_envelope": [
        "allocation envelope", "split the budget", "allocate the budget", "divide the budget", "distribute the budget", "budget across districts",
        "budget by severity", "funding envelope", "share the funding", "allocate funding",
    ],
    "import_jiaf_inputs": [
        "jiaf input", "jiaf inputs", "import jiaf", "load the jiaf", "sector pin file", "sectoral pin", "jiaf worksheet", "hno dataset",
        "people in need by sector", "sector inputs",
    ],
    "compute_jiaf_preliminary": [
        "preliminary joint pin", "preliminary pin", "mosaic method", "joint overall pin", "preliminary intersectoral severity", "jiaf flags",
        "pin flags", "highest sectoral pin", "compute the jiaf", "jiaf preliminary",
    ],
    "record_jiaf_decisions": ["record the jiaf decision", "jiaf decisions", "final pin decision", "agreed severity", "flagged unit decision", "which sector pin"],
    "get_jiaf_decisions": ["show the jiaf decisions", "stored jiaf decisions"],
    "finalize_jiaf_results": ["final pin", "final joint overall pin", "finalize the jiaf", "finalise the jiaf", "jiaf final results", "pending flagged units"],
    "compute_jiaf_patterns": ["jiaf patterns", "intersectoral patterns", "workspace 3c", "pin correlation between sectors", "sectors driving the needs",
                              "needs patterns and linkages"],
    "record_jiaf_setup": ["jiaf set-up", "jiaf setup", "record the jiaf", "sector alignment", "jiaf scope", "manual edition"],
    "get_jiaf_setup": ["show the jiaf set-up", "jiaf setup record", "what jiaf scope"],
    "analyze_critical_links": [
        "critical link", "critical links", "bottleneck", "bottlenecks", "single point of failure", "which roads matter most",
        "which road is most important", "roads the routes depend on", "route dependence",
    ],
    "import_humanitarian_table": [
        "import ipc", "ipc table", "ipc phase file", "ipc classification file", "import inform", "inform risk table", "inform risk file",
        "unosat damage", "unosat points", "import the damage points", "load the ipc", "load the inform",
    ],
    "apply_humanitarian_look": [
        "show the severity on the map", "map the severity", "style the severity", "colour by severity", "color by severity",
        "map the people in need", "show people in need on the map", "map the gap", "style the presence gap", "map the ranking",
        "style the ranking", "show the rank on the map",
        "show the jiaf severity", "map the jiaf", "jiaf on the map", "map the severity phases", "which districts still need a decision",
        "which units are pending", "where the group still has to decide", "map the pending", "colour the phases", "color the phases",
        "highlight the worst", "show the worst", "areas that need help most", "where help is needed most", "most in need on the map",
    ],
    "aggregate_survey_indicator": [
        "survey results by", "survey indicator", "weighted survey", "survey weights", "household survey results", "proportion of households",
        "share of households", "percentage of households",
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
    # Added 2026-09-13, live user report: "show live incedent in jordan... natural, crime,
    # haszard" -- fetch_gdacs_disaster_alerts scored zero relevance for this phrasing (its
    # description names specific hazard TYPES -- earthquakes, floods, wildfires -- but never
    # the generic words "disaster"/"hazard"/"incident" a real user reaches for first). The
    # single-word "hazard"/"disaster"/"incident"/"wildfire" entries below exist specifically so
    # _expand_query_with_fuzzy_corrections() (see its docstring) has something to land a
    # corrected "haszard"->"hazard" or "incedent"->"incident" on -- bare-substring matching
    # alone still can't see a misspelled word, but the fuzzy-correction pass runs before this
    # check and appends the corrected form to the string these aliases are matched against.
    # rule 48 (prompts.py) is the complementary fix for when the tool IS already a candidate
    # but the model doesn't know to reach for it.
    "fetch_gdacs_disaster_alerts": [
        "disaster alert", "current disaster", "live disaster", "ongoing disaster",
        "disaster incident", "hazard alert", "what disasters", "natural disaster",
        "hazard", "disaster", "emergency",
    ],
    "fetch_nasa_eonet_events": [
        "natural event", "live event", "current event", "live hazard",
        "current hazard", "natural incident", "live incident", "ongoing hazard",
        "what hazards", "hazard incident", "hazard", "incident",
    ],
    "fetch_nasa_active_fires": [
        "active fire", "live fire", "fire detection", "current wildfire",
        "wildfire location", "fire alert", "wildfire",
    ],
    # Plain-language styling requests share no words with the style tools' names ("make the clinics stand out",
    # "colour the districts by how many people live there"); measured before this entry: several got no style tool at all.
    "get_layer_extent": [
        "extent", "bounding box", "bbox", "wgs84", "in degrees", "lat/lon", "search_stac_satellite_imagery", "fetch_building_footprints",
        "fetch_osm_features", "fetch_worldpop_population", "sentinel", "satellite scenes", "building footprints", "inside it",
    ],
    "apply_graduated_style": [
        "colour the districts by", "color the districts by", "shade the districts", "darker where", "darker the more",
        "colour by how many", "color by how many", "from light to dark", "light to dark", "darker for higher",
        "show how much", "show how many",
    ],
    "apply_graduated_symbol_style": [
        "bigger dots", "bigger circles", "larger dots", "larger circles", "bigger the more", "size by", "scale the dots",
        "scale the circles", "dot size", "bigger symbols",
    ],
    "apply_heatmap_style": [
        "crowded", "crowding", "where people are concentrated", "where most", "concentrated", "density map", "hot spots",
        "hotspots", "busy areas", "clusters of",
    ],
    "apply_categorized_style": [
        "different colour for each", "different color for each", "each type in its own colour", "each type in its own color",
        "colour by type", "color by type", "colour each", "color each", "separate colours", "separate colors",
    ],
    "change_layer_color": [
        "make it red", "make them red", "in red", "in blue", "in green", "in dark", "in light", "in pale", "make it stand out",
        "make them stand out", "stand out", "change the colour", "change the color", "recolour", "recolor",
    ],
    "apply_labels": [
        "put the names", "show the names", "names on the map", "write the names", "name next to", "label each",
        "show the name of each",
    ],
    "set_layer_transparency": [
        "see-through", "see through", "less solid", "so i can see underneath", "so i can see what is below",
        "fade the", "more transparent",
    ],
    "auto_arrange_layer_order": [
        "easier to read", "tidy the map", "clean up the map", "declutter", "map is cluttered", "looks messy", "hide the clutter",
    ],
}
# A live user report typo'd BOTH "hazard" -> "haszard" and "incident" -> "incedent" in the
# same query (2026-09-13) -- the alias entries above are exact-substring, so a misspelled
# word matches nothing at all, no matter how close. Scoped narrowly to avoid the false-positive
# risk of fuzzy-matching against the full ~169-tool vocabulary: only checked against this small,
# curated set of words that actually gate real capability (hazard/disaster reporting), only for
# query words of 5+ characters (short words have too many close neighbors to be a safe fuzzy
# target), and only ever ADDS a corrected word alongside the original -- never replaces or
# removes a query word, so a query that was already scoring correctly is unaffected.
_FUZZY_TYPO_VOCAB = {
    "hazard", "hazards", "disaster", "disasters", "incident", "incidents",
    "wildfire", "wildfires", "earthquake", "earthquakes", "flood", "floods",
    "drought", "droughts", "volcano", "volcanoes", "cyclone", "cyclones",
    "emergency", "emergencies",
}
_FUZZY_TYPO_MIN_WORD_LEN = 5
_FUZZY_TYPO_CUTOFF = 0.8


def _expand_query_with_fuzzy_corrections(query_words: set, query_lower: str) -> str:
    """Returns query_lower with a space-joined tail of any fuzzy-corrected words appended,
    for use as the alias-matching string. Does not mutate query_words (name/description
    scoring is unaffected -- see _FUZZY_TYPO_VOCAB's docstring above for why this stays
    narrowly scoped to the alias-matching path only)."""
    corrections = []
    for word in query_words:
        if len(word) < _FUZZY_TYPO_MIN_WORD_LEN or word in _FUZZY_TYPO_VOCAB:
            continue
        match = difflib.get_close_matches(
            word, _FUZZY_TYPO_VOCAB, n=1, cutoff=_FUZZY_TYPO_CUTOFF
        )
        if match:
            corrections.append(match[0])
    if not corrections:
        return query_lower
    return query_lower + " " + " ".join(corrections)
# Score contribution for an alias phrase match -- comparable to a name match
# (10), since these are curated synonyms for a specific known gap rather than
# an incidental substring hit, but not higher (a real name/description match
# should still win a tie against an alias match).
# Verbs and nouns that appear in dozens of tool names ("generate_*", "calculate_*", "*_layer"). A request that says "generate a buffer"
# must not get +10 for generate_html_dashboard, generate_report and generate_mapping_task_grid; the distinctive word (buffer,
# dashboard, report) still scores. Found by measurement on a long request: these verbs alone filled the tool list with unrelated tools.
_GENERIC_NAME_WORDS = frozenset({"generate", "calculate", "create", "apply", "get", "set", "add", "fetch", "run", "export", "extract",
                                 "analyze", "analyse", "layer", "layers", "map", "data", "style", "report", "analysis", "tool"})
_LONG_QUERY_WORDS = 25
_LONG_QUERY_MIN_SCORE = 6
_DESCRIPTION_HIT_CAP = 4        # at most +8 from description words, however long the request
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

    def filter_relevant_tools(self, user_query: str, top_k: int = 40, carry_over_tools=None) -> List[Dict]:
        """Returns top_k relevant tool schemas matching user query terms.

        `carry_over_tools`: names of tools the PREVIOUS turn used. A short follow-up ("EPSG:3857", "yes, the second one") shares no
        vocabulary with any tool, so scoring on the new message alone dropped the tool the conversation was in the middle of: in the
        rc17 hand test (2026-10-06) the model answered the CRS question with "add_point_layer is unavailable" because it was not in
        the turn's tool list, and the rc16 hint telling it to call add_point_layer again could not help. Names that are not
        registered tools are ignored."""
        if len(self.full_schema_list) <= top_k:
            return self.full_schema_list

        query_lower = user_query.lower()
        # _STOPWORDS removed here only -- query_lower (used by the separate curated-alias
        # check below) keeps every word, since a multi-word alias phrase like "rank the
        # districts" is matched as a whole substring, not word-by-word.
        query_tokens = set(re.findall(r'\w+', query_lower))
        query_words = set()
        for token in query_tokens:
            if token not in _STOPWORDS:
                query_words.add(token)
            if "_" in token:
                query_words.update(w for w in token.split("_") if w not in _STOPWORDS)

        # Alias matching only -- see _FUZZY_TYPO_VOCAB's docstring. Never touches query_words
        # itself, so name/description scoring (and every existing test asserting on it) is
        # unaffected; only the alias substring check below sees the corrected words.
        alias_query_lower = _expand_query_with_fuzzy_corrections(query_words, query_lower)

        # Tools explicitly requested by exact name in user_query/follow-up prompt get guaranteed inclusion
        explicit_tool_names = {
            t.get("function", {}).get("name", "")
            for t in self.full_schema_list
            if t.get("function", {}).get("name", "").lower() in query_lower
            and len(t.get("function", {}).get("name", "")) >= 4
        }

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
        } | explicit_tool_names
        known_names = {t.get("function", {}).get("name", "") for t in self.full_schema_list}
        # Tools the request's DATA SOURCES and ACTIONS require (core/agent/capabilities.py), claimed before any description-word
        # scoring: a long request used to fill the slots with weak description matches (a dashboard, PDF-table and NDWI tool for a
        # water-service request) and leave out the tools the steps actually needed. Bounded, and only registered names count.
        try:
            from ..agent.capabilities import required_tools
            always_include |= {n for n in required_tools(user_query) if n in known_names}
            from ..agent.capabilities import is_multi_step, uncovered_capabilities
            if (uncovered_capabilities(user_query) or is_multi_step(user_query)) and "find_tools" in known_names:
                always_include.add("find_tools")      # a step with no dedicated tool, or a workflow: let the model look tools up
            if is_multi_step(user_query) and "run_steps" in known_names:
                always_include.add("run_steps")       # a workflow: let the model send a whole known chain in one round trip
                from ..agent.capabilities import needed_capabilities
                from ..agent.chains import chains_for
                for chain in chains_for([c for c, _t, _v in needed_capabilities(user_query)]):
                    # run_steps only accepts tools that were offered, so offer the chain's own
                    always_include |= {st["tool"] for st in chain["steps"] if st["tool"] in known_names}
        except Exception:  # nosec B110 (best-effort: failure is non-fatal)
            pass
        # At most six carried tools, so a long previous turn cannot crowd the relevant ones out of top_k.
        always_include |= {n for n in tuple(carry_over_tools or ())[:6] if n in known_names and n != "execute_pyqgis_script"}
        _FALLBACK_TOOL = "execute_pyqgis_script"

        # Sort deterministically by tool name instead of randomizing -- 2026-09-19, live-
        # verified follow-up to the "hi" fix above. random.shuffle() reordered the whole tool
        # list on every single call, which meant the serialized `tools` array in the request
        # body was almost never byte-identical between two calls even when they carried the
        # exact same tool SET, defeating prefix-based caching for that segment of the request
        # (Gemini's implicit caching -- automatic on 2.5+ models, no config needed -- discounts
        # a repeated prefix by 90%, confirmed against ai.google.dev/gemini-api/docs/caching and
        # ai.google.dev/gemini-api/docs/pricing, not assumed). Live-measured via a real 12-turn
        # Gemini session after this change: 6 of 23 calls reported real cached_tokens in the
        # response, a mechanism no run before this fix ever showed evidence of. Ties (0-score
        # filler tools) now break alphabetically, replacing the deliberate per-call randomness
        # the removed comment above described -- a real trade-off, not a pure improvement: that
        # randomness existed specifically so the same handful of filler tools didn't get a
        # permanent, arbitrary advantage every time nothing else matched (see the git history of
        # this line). Deterministic tie-breaking reintroduces that specific bias in exchange for
        # the caching win -- acceptable since filler tools are, by definition, not a real match
        # for the query either way, but worth knowing if that older bias ever matters again.
        shuffled = sorted(list(self.full_schema_list), key=lambda x: x.get("function", {}).get("name", ""))

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
            name_words = set(name.lower().split("_")) - _GENERIC_NAME_WORDS
            desc_words = set(re.findall(r"\w+", desc))

            score = 0
            # Name match score
            if query_words & {w for w in name_words if len(w) > 2}:
                score += 10

            # Description match score -- capped: in a 70-100 word request nearly every tool description shares a few ordinary words
            # ("all", "points", "layer"), so uncapped +2 per word let description noise outrank real name and alias matches.
            description_hits = sum(1 for word in query_words if len(word) > 2 and word in desc_words)
            score += 2 * min(description_hits, _DESCRIPTION_HIT_CAP)

            # Curated alias/synonym match score
            for alias in _TOOL_ALIASES.get(name, []):
                if alias in alias_query_lower:
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
        # Drop zero-score filler tools even on a partial-signal query, not just the
        # nothing_else_matched case -- 2026-09-19 follow-up to the "hi" fix above. A query
        # that scores real relevance against 12 tools was still padding the returned set out
        # to the full top_k=40 with 0-score tools purely because they happened to sort within
        # the slice, which is the same wasted-token problem as the all-zero case, just
        # partially masked by the real matches sitting alongside it. Since scored_tools is
        # sorted descending, every positive-score tool already sorts before every 0-score
        # tool, so slicing to top_k first and then dropping 0-scores is equivalent to (not a
        # behavior change from) filtering positives first and slicing second -- this is a
        # strict simplification/extension of the prior nothing_else_matched-only logic, not a
        # separate code path, and unconditionally applies to every query now.
        # A long request shares an ordinary word or two with most tool descriptions; those one-word overlaps are noise, not relevance.
        # For a request of more than _LONG_QUERY_WORDS words a tool must score at least _LONG_QUERY_MIN_SCORE (a name or alias match,
        # three description words, or a capability the request names) to take a slot. Short requests keep the old rule (score > 0).
        floor = _LONG_QUERY_MIN_SCORE if len(user_query.split()) > _LONG_QUERY_WORDS else 1
        return [tool for score, tool in scored_tools[:top_k] if score >= floor]
