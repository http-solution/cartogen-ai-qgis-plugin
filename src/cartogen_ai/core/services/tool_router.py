"""
Semantic Tool Router & Retrieval Engine for Cartogen AI.
Filters top-k relevant tool schemas based on user query keywords and intent matching
to prevent LLM system prompt context overload.
"""

import contextlib
import difflib
import functools
import json
import os
import re
import unicodedata


# Curated phrase synonyms for tools whose real-world paraphrases don't share
# vocabulary with their name/description -- e.g. "rank the districts by how
# bad the situation is" shares no words with calculate_severity_index's name.
# Since PLAN-042 step 2 each tool declares its own phrases beside its
# @register_tool (keywords=[...], see tools/registry.py) and shared synonym
# groups live in routing_concepts.json; this dict is only the older central
# place and is empty. Keep the why-comment with the phrases when you add one.
# Routing-only signals: kept out of the tool descriptions, which are sent to the
# model on every call where the tool is selected.
_TOOL_ALIASES: dict[str, list[str]] = {
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


_CONCEPTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "routing_concepts.json")
_concepts_cache: dict = {}
_CONCEPT_PREFIX = "concept:"   # not "@": existing aliases such as "@2" (raster calculator) start with it


def _concepts():
    """Shared synonym groups (routing_concepts.json): a phrase list written once and named by "concept:name" in a tool's keywords, so a new
    synonym is one line of data for every tool that uses the group (PLAN-042 step 3). Empty if the file cannot be read."""
    if not _concepts_cache:
        with contextlib.suppress(Exception), open(_CONCEPTS_PATH, encoding="utf-8") as handle:
            _concepts_cache.update(json.load(handle))
    return _concepts_cache


def expand_phrases(phrases):
    """The phrases with every "concept:name" replaced by that concept's phrases; an unknown concept adds nothing (a test fails on it)."""
    out = []
    for phrase in phrases:
        out.extend(_concepts().get(phrase[len(_CONCEPT_PREFIX):], ()) if phrase.startswith(_CONCEPT_PREFIX) else (phrase,))
    return tuple(out)


_LANGUAGES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "routing_languages.json")
_languages_cache: dict = {}
# Arabic spellings that vary between writers: alef maqsura / ya, ta marbuta / ha, tatweel. Harakat and the hamza on an alef are combining
# marks, removed by the accent strip below, so "أين" and "اين", "مستشفى" and "مستشفي" meet at the same folded text.
_FOLD_TABLE = str.maketrans({"\u0649": "\u064a", "\u0629": "\u0647", "\u0640": ""})


@functools.cache
def fold(text):
    """Lower-case, accent-free, Arabic-spelling-tolerant form of a phrase or request, used on BOTH sides of a phrase match, so French
    accents ("hôpital" / "hopital") and Arabic diacritics or alef forms do not decide whether a phrase hits. English text is unaffected."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c)).translate(_FOLD_TABLE)


def _language_phrases(name):
    """Arabic and French phrases for a tool from routing_languages.json ({"ar": {tool: [phrases]}, "fr": {...}}); a fluent reviewer can edit
    one file per language. Empty if the file cannot be read."""
    if not _languages_cache:
        with contextlib.suppress(Exception), open(_LANGUAGES_PATH, encoding="utf-8") as handle:
            _languages_cache.update(json.load(handle))
    return tuple(p for table in _languages_cache.values() for p in table.get(name, ()))


def _declared_keywords(name):
    """Phrases a tool declares beside its own @register_tool (PLAN-042 step 2), concept references expanded; empty if the registry is
    unavailable."""
    with contextlib.suppress(Exception):
        from ..agent.tools.registry import TOOL_KEYWORDS
        return expand_phrases(TOOL_KEYWORDS.get(name, ()))
    return ()


def routing_phrases(name):
    """Every curated phrase for a tool: its declared keywords plus any in _TOOL_ALIASES, concept references expanded."""
    return (*expand_phrases(_TOOL_ALIASES.get(name, ())), *_declared_keywords(name), *_language_phrases(name))


def routing_phrase_tools():
    """Names of the tools that have at least one curated phrase."""
    names = set(_TOOL_ALIASES)
    _language_phrases("")    # loads the language file
    for table in _languages_cache.values():
        names |= set(table)
    with contextlib.suppress(Exception):
        from ..agent.tools.registry import TOOL_KEYWORDS
        names |= set(TOOL_KEYWORDS)
    return sorted(names)


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

DEFAULT_TOP_K = 28
_MIN_TOP_K, _MAX_TOP_K = 12, 60


def configured_top_k() -> int:
    """Tools offered per request, from QGIS settings, clamped to a sane range; DEFAULT_TOP_K outside QGIS or on a bad value."""
    try:
        from qgis.core import QgsSettings
        from ...infrastructure.settings_keys import SETTINGS_TOOL_ROUTER_TOP_K
        value = int(QgsSettings().value(SETTINGS_TOOL_ROUTER_TOP_K, DEFAULT_TOP_K))
    except Exception:
        return DEFAULT_TOP_K
    return max(_MIN_TOP_K, min(_MAX_TOP_K, value))
_LONG_QUERY_MIN_SCORE = 6
_DESCRIPTION_HIT_CAP = 4        # at most +8 from description words, however long the request
# Was 10, the same as ONE generic name-word match. As the registry grew past 230 tools, more than 40 of them had "layer", "create" or "add" in
# their name, and for a short request ("create layer for Jordan ADM1") the curated alias tool tied with all of them and lost its slot to
# the alphabetical tie-break: adding the M2 tools made fetch_geoboundaries drop out. A curated phrase is the strongest signal the router
# has, so it now outranks a name-word match (10) plus a full set of description hits (+8). Guarded by tests/test_tool_router_basics.py.
_ALIAS_MATCH_SCORE = 25

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


_PROCESSING_GENERIC_TOOLS = frozenset({"find_processing_algorithm", "run_allowlisted_processing_algorithm"})


def _query_terms(user_query):
    """(lower-cased query, is it a long request, scoring words). _STOPWORDS are removed from the scoring words only: the lower-cased
    query keeps every word, since a multi-word curated alias like "rank the districts" is matched as a whole substring, not word by word."""
    query_lower = user_query.lower()
    long_query = len(user_query.split()) > _LONG_QUERY_WORDS
    query_tokens = set(re.findall(r'\w+', query_lower))
    query_words = set()
    for token in query_tokens:
        if token not in _STOPWORDS:
            query_words.add(token)
        if "_" in token:
            query_words.update(w for w in token.split("_") if w not in _STOPWORDS)
    return query_lower, long_query, query_words


def _add_capability_tools(always_include, user_query, known_names):
    """Adds to `always_include` (in place) the tools the request's DATA SOURCES and ACTIONS require (core/agent/capabilities.py), claimed
    before any description-word scoring: a long request used to fill the slots with weak description matches (a dashboard, PDF-table and
    NDWI tool for a water-service request) and leave out the tools the steps actually needed. Bounded, and only registered names count.
    Any failure inside keeps what was already added, as the inline code this was lifted from did."""
    with contextlib.suppress(Exception):
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


def _algorithm_topic_match(user_query):
    """A request that describes WHAT is wanted ("fill the gaps in my elevation raster", "which areas are visible from this point") rather
    than naming an algorithm: the topic index (core/agent/algorithm_topics.py) finds the approved algorithms that fit, and the two generic
    Processing tools are offered, so the model can search and run them. Without this only an algorithm's own name reached them (rc45 smoke
    run: every test prompt spelled the name and id)."""
    matched = False
    with contextlib.suppress(Exception):
        from ..agent.algorithm_topics import algorithms_for_task
        from ..agent.algorithm_topics import rank as _rank_algorithms
        matched = bool(_rank_algorithms(user_query, limit=1))
        if not matched:
            # a request the task register recognises, whose task names approved algorithms, is told about them (task_directive), so the
            # two generic Processing tools must be among the offered ones for that advice to be usable
            from ..agent.task_matcher import classify
            verdict = classify(user_query)
            best = verdict.get("best")
            matched = bool(best and not (verdict["ambiguous"] and verdict["reason"] == "below confidence floor")
                           and algorithms_for_task(best.get("id")))
    return matched


def _score_tool(name, desc, query_words, long_query, alias_query_lower, algorithm_topic_match):
    """Relevance of one (non always-included) tool to the request: name words +10, description words +2 each (capped for a long request),
    curated aliases +_ALIAS_MATCH_SCORE each, and the two generic Processing tools +_ALIAS_MATCH_SCORE on a topic match."""
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
    # Generic words are discounted only for a LONG request, which is where the measurement that justified it was made. For a
    # short one ("zoom to the layer", "create layer for Jordan ADM1", "remove the layer X") "layer", "add", "export", "create" ARE the
    # signal: from rc23 on the discount applied to every request, add_layer_from_path, remove_layer, zoom_to_layer, export_layer and
    # the other layer tools stopped being offered, and ties were then broken alphabetically (apply_*, calculate_*). Found by replaying
    # 40 plain requests against every release (tests/test_tool_router_basics.py is the permanent guard).
    name_words = set(name.lower().split("_"))
    if long_query:
        name_words -= _GENERIC_NAME_WORDS
    desc_words = set(re.findall(r"\w+", desc))

    score = 0
    # Name match score
    if query_words & {w for w in name_words if len(w) > 2}:
        score += 10

    # Description match score -- capped: in a 70-100 word request nearly every tool description shares a few ordinary words
    # ("all", "points", "layer"), so uncapped +2 per word let description noise outrank real name and alias matches.
    description_hits = sum(1 for word in query_words if len(word) > 2 and word in desc_words)
    score += 2 * (min(description_hits, _DESCRIPTION_HIT_CAP) if long_query else description_hits)

    # Curated alias/synonym match score
    for alias in routing_phrases(name):
        if fold(alias) in alias_query_lower:
            score += _ALIAS_MATCH_SCORE
    if algorithm_topic_match and name in _PROCESSING_GENERIC_TOOLS:
        score += _ALIAS_MATCH_SCORE
    return score


class ToolRouter:
    """Keyword & intent-based tool schema selector."""

    def __init__(self, full_schema_list: list[dict]):
        self.full_schema_list = full_schema_list

    def filter_relevant_tools(self, user_query: str, top_k: int = DEFAULT_TOP_K, carry_over_tools=None) -> list[dict]:
        """Returns top_k relevant tool schemas matching user query terms.

        `carry_over_tools`: names of tools the PREVIOUS turn used. A short follow-up ("EPSG:3857", "yes, the second one") shares no
        vocabulary with any tool, so scoring on the new message alone dropped the tool the conversation was in the middle of: in the
        rc17 hand test (2026-10-06) the model answered the CRS question with "add_point_layer is unavailable" because it was not in
        the turn's tool list, and the rc16 hint telling it to call add_point_layer again could not help. Names that are not
        registered tools are ignored."""
        if len(self.full_schema_list) <= top_k:
            return self.full_schema_list

        query_lower, long_query, query_words = _query_terms(user_query)

        # Alias matching only -- see _FUZZY_TYPO_VOCAB's docstring. Never touches query_words
        # itself, so name/description scoring (and every existing test asserting on it) is
        # unaffected; only the alias substring check below sees the corrected words.
        alias_query_lower = fold(_expand_query_with_fuzzy_corrections(query_words, query_lower))

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
        _add_capability_tools(always_include, user_query, known_names)
        # At most six carried tools, so a long previous turn cannot crowd the relevant ones out of top_k.
        always_include |= {n for n in tuple(carry_over_tools or ())[:6] if n in known_names and n != "execute_pyqgis_script"}
        fallback_tool = "execute_pyqgis_script"
        # A request that describes WHAT is wanted ("fill the gaps in my elevation raster", "which areas are visible from this point")
        # rather than naming an algorithm: the topic index (core/agent/algorithm_topics.py) finds the approved algorithms that fit, and the
        # two generic Processing tools are offered, so the model can search and run them. Without this only an algorithm's own name
        # reached them (rc45 smoke run: every test prompt spelled the name and id).
        algorithm_topic_match = _algorithm_topic_match(user_query)

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
        shuffled = sorted(self.full_schema_list, key=lambda x: x.get("function", {}).get("name", ""))

        scored_tools = []
        for tool_obj in shuffled:
            fn = tool_obj.get("function", {})
            name = fn.get("name", "")
            desc = fn.get("description", "").lower()

            if name in always_include:
                scored_tools.append((1000, tool_obj))
                continue

            score = _score_tool(name, desc, query_words, long_query, alias_query_lower, algorithm_topic_match)

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
            if tool.get("function", {}).get("name") not in always_include | {fallback_tool}
        ]
        nothing_else_matched = not other_scores or max(other_scores) <= 0
        if nothing_else_matched:
            scored_tools = [
                (1000, tool) if tool.get("function", {}).get("name") == fallback_tool else (score, tool)
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
        chosen = [tool for score, tool in scored_tools[:top_k] if score >= floor]
        # find_tools is always offered, on top of top_k so it takes no slot from a relevant tool (PLAN-042 step 4): the offered tools are
        # a selection, and it is how the model asks for one the selection missed. Measured 2026-10-30: the best score was 10 or more for
        # all 493 test requests, so a "weak match" trigger never fires; the miss that mattered ("list medical service") was a confident
        # wrong answer.
        if "find_tools" in known_names and not any(t.get("function", {}).get("name") == "find_tools" for t in chosen):
            chosen.extend(t for t in self.full_schema_list if t.get("function", {}).get("name") == "find_tools")
        return chosen
