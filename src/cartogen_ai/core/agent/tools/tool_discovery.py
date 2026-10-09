# -*- coding: utf-8 -*-
"""find_tools: lets the model ask for the tools a step needs when the ones it was given do not cover it.

The tool router sends a bounded list per request. When the model identifies a step that list does not cover (say, contour lines or
splitting a road by zones) it used to have two bad options: give up or improvise with a script. find_tools returns the matching
tools by name and description, and the agent loop adds their schemas to the tools offered for the rest of the turn, so the next call
can use them. Read-only; it never runs anything."""
import re

from .registry import register_tool, TOOLS_SCHEMA

MAX_RESULTS = 8
_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset({"the", "a", "an", "and", "or", "of", "to", "for", "with", "in", "on", "by", "from", "tool", "tools", "need", "needs",
                   "that", "this", "how", "can", "do", "i", "me", "my", "all", "any"})


def rank_tools(query, schemas, limit=MAX_RESULTS):
    """[(score, name, description)] best first for `query` over `schemas` (OpenAI-style function schemas). Name words count 4x a
    description word; capability-table tools for the named steps come first. Pure."""
    words = {w for w in _WORD.findall((query or "").lower()) if w not in _STOP and len(w) > 2}
    try:
        from ..capabilities import required_tools
        preferred = required_tools(query)
    except Exception:
        preferred = []
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
        if score > 0:
            scored.append((score, name, desc))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored[:limit]


@register_tool(
    "find_tools",
    "Look up which tools can do a step you were not given a tool for (for example 'contour lines', 'split a line by polygons', "
    "'download elevation'). Returns the best matching tool names with a one-line description each, and makes them available for the "
    "rest of this request. Use it BEFORE writing a script. It only searches; it changes nothing.",
    {"type": "object", "properties": {"need": {"type": "string", "description": "The step you need to do, in plain words."}},
     "required": ["need"]},
)
def find_tools(need):
    matches = rank_tools(need, TOOLS_SCHEMA)
    if not matches:
        return {"success": True, "tools": [], "tool_names": [],
                "note": "No registered tool matches that step. Say so rather than improvising; a script is a last resort and must be disclosed."}
    return {"success": True, "tool_names": [name for _s, name, _d in matches],
            "tools": [{"name": name, "does": (desc.split(". ")[0])[:160]} for _s, name, desc in matches],
            "note": "These tools are now available for the rest of this request."}
