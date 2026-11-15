"""find_tools: lets the model ask for the tools a step needs when the ones it was given do not cover it.

The tool router sends a bounded list per request. When the model identifies a step that list does not cover (say, contour lines or
splitting a road by zones) it used to have two bad options: give up or improvise with a script. find_tools returns the matching
tools by name and description, and the agent loop adds their schemas to the tools offered for the rest of the turn, so the next call
can use them. Read-only; it never runs anything."""
import contextlib
import json
import re
from pathlib import Path

from .registry import register_tool, TOOLS_SCHEMA

MAX_RESULTS = 8
PHRASE_SCORE = 12   # above a name-word hit (4) so a curated phrase outranks incidental word overlap
_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset({"the", "a", "an", "and", "or", "of", "to", "for", "with", "in", "on", "by", "from", "tool", "tools", "need", "needs",
                   "that", "this", "how", "can", "do", "i", "me", "my", "all", "any"})


_SYNONYMS_PATH = Path(__file__).resolve().parents[2] / "services" / "routing_synonyms.json"
_synonyms_cache: dict[str, list[str]] = {}


def _synonyms():
    """{plain word: [words the tool names and descriptions use for it]} from core/services/routing_synonyms.json; {} if unreadable."""
    if not _synonyms_cache:
        with contextlib.suppress(Exception), open(_SYNONYMS_PATH, encoding="utf-8") as handle:
            _synonyms_cache.update(json.load(handle))
    return _synonyms_cache


def expand_words(words):
    """`words` plus the tool-vocabulary words their plain-language synonyms map to ("colour" -> style, graduated, ...). Pure given the file.
    Measured 2026-11-01: a need written as "colour polygons by value" never reached apply_graduated_style because no tool name or description says
    "colour"; the same hole the router has, in the one place the model writes the wording itself."""
    table = _synonyms()
    return set(words).union(*(table.get(word, ()) for word in words))


def rank_tools(query, schemas, limit=MAX_RESULTS):
    """[(score, name, description)] best first for `query` over `schemas` (OpenAI-style function schemas). Name words count 4x a
    description word; each curated routing phrase found in the query adds PHRASE_SCORE; capability-table tools for the named steps come first. Pure."""
    words = expand_words({w for w in _WORD.findall((query or "").lower()) if w not in _STOP and len(w) > 2})
    try:
        from ..capabilities import required_tools
        preferred = required_tools(query)
    except Exception:
        preferred = []
    query_lower = (query or "").lower()
    try:
        from ...services.tool_router import routing_phrases
    except Exception:
        routing_phrases = None
    scored = []
    for schema in schemas:
        fn = schema.get("function", {}) if isinstance(schema, dict) else {}
        name, desc = fn.get("name", ""), str(fn.get("description", ""))
        if not name or name == "find_tools":
            continue
        name_words = set(name.lower().split("_"))
        desc_words = set(_WORD.findall(desc.lower()))
        score = 4 * len(words & name_words) + len(words & desc_words)
        if name in preferred:
            score += 20 - preferred.index(name)
        # The curated phrases the router also scores (a tool's keywords= and its shared concept groups): without them a wording that
        # shares no word with the tool's name or description ("list medical services", "any dispensary") found calculate_service_area
        # and list_bookmarks instead of the OSM and geocoding tools (measured 2026-10-30).
        if routing_phrases is not None:
            score += PHRASE_SCORE * sum(1 for phrase in routing_phrases(name) if phrase in query_lower)
        if score > 0:
            scored.append((score, name, desc))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored[:limit]


@register_tool(
    "find_tools",
    "Look up which tools can do a step you were not given a tool for (for example 'contour lines', 'split a line by polygons', "
    "'download elevation'). Returns the best matching tool names with a one-line description each, and makes them available for the "
    "rest of this request. Use it BEFORE writing a script. It only searches; it changes nothing.",
    {"type": "object", "properties": {"need": {"type": "string", "description": "The operation you need, in plain English words, even when the user wrote in another language (tool names and descriptions are English, so an Arabic or French phrase finds nothing). Name the operation, not the goal: 'graduated colour style for polygons by a number', 'clip lines to polygons', 'count points in each polygon', 'turn a layer on and off'."}},
     "required": ["need"]},
    keywords=[
        "which tool", "what tool", "is there a tool", "is there a way to", "what can you do", "list the tools", "what tools",
    ],
)
def find_tools(need):
    matches = rank_tools(need, TOOLS_SCHEMA)
    if not matches:
        return {"success": True, "tools": [], "tool_names": [],
                "note": "No registered tool matches that step. Say so rather than improvising; a script is a last resort and must be disclosed."}
    return {"success": True, "tool_names": [name for _s, name, _d in matches],
            "tools": [{"name": name, "does": (desc.split(". ")[0])[:160]} for _s, name, desc in matches],
            "note": "These tools are now available for the rest of this request."}


@register_tool(
    "run_steps",
    "Run several tool calls in order in ONE step instead of one model turn each. Use it only when you already know every argument "
    "of the whole chain (for example you choose the output layer names yourself). Each step is {tool, arguments}; an argument "
    "may be the whole-string reference \"$2.layer_name\" (field `layer_name` of step 2's result) or \"$prev.layer_name\". Steps "
    "run one at a time through the normal tool path, so confirmations and safety checks still apply; the run STOPS at the first "
    "error or the first call waiting for the user's Confirm and reports exactly which steps ran. At most 8 steps; no deleting "
    "tools; do not nest run_steps. If a later step depends on something you must look at first, make separate calls instead.",
    {"type": "object", "properties": {
        "steps": {"type": "array", "description": "Ordered steps.", "items": {"type": "object", "properties": {
            "tool": {"type": "string", "description": "Tool name."},
            "arguments": {"type": "object", "description": "That tool's arguments."}}, "required": ["tool"]}}},
     "required": ["steps"]},
)
def run_steps(steps=None):
    # The agent loop runs this itself (it needs the turn's tool path, guard and callbacks); reaching here means it was called
    # outside a turn, where there is nothing to run the steps against.
    return {"error": "run_steps can only be used inside an agent turn."}
