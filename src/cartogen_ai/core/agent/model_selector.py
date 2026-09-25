# -*- coding: utf-8 -*-
"""
Complexity-based automatic model selection for Cartogen AI.
Picks between a cheaper/faster and a more capable model from whatever live
model list a provider actually returned -- never invents a model ID.
"""

import re

AUTO_SENTINEL = "auto"

_NON_CHAT_DENYLIST = ["embed", "whisper", "tts", "dall-e", "dalle", "moderation", "guard", "safety", "image", "audio"]


def filter_chat_model_ids(model_ids):
    """Drops obviously non-chat model IDs (embeddings, TTS, moderation, etc.)
    so the model dropdown isn't cluttered with entries that will just 404 on
    a chat completions call."""
    return sorted({
        m for m in model_ids
        if m and not any(bad in m.lower() for bad in _NON_CHAT_DENYLIST)
    })

# Phrases that indicate the request explicitly chains multiple steps.
_MULTI_STEP_PHRASES = [
    " and then", " after that", " then ", "step by step", "step-by-step",
    "multi-step", "create a plan", "workflow",
]
# Words implying "more than one of something" -- a real complexity signal on
# their own, unlike a single GIS noun/verb which a trivial request can also contain.
_QUANTITY_SIGNALS = ["multiple", "several", "each of", "each one"]
# Individual GIS operations. One of these appearing is not evidence of
# complexity by itself ("list layers" is trivial) -- two or more distinct
# operations named in one request usually means real multi-step work.
_OPERATION_VERBS = [
    "buffer", "intersect", "join", "analyze", "analysis", "calculate",
    "compare", "reproject", "classify", "merge", "clip", "dissolve",
]

# Matched against whole name TOKENS (split on every non-alphanumeric), not substrings. A substring
# match made "mini" hit every "gemini-*" model, so all of Gemini's models scored as "cheap". Found
# 2026-09-25 while running the picker on a real Gemini model list, once the provider fix below made
# its picks actually take effect for the first time.
_CHEAP_MID = {"mini", "flash", "haiku", "small", "instant"}    # small but still dependable at tool calls
_CHEAP_LOW = {"nano", "lite", "8b", "9b", "12b", "20b"}        # cheapest tier; weakest at choosing among ~180 tools
_CAPABLE_KEYWORDS = {"pro", "ultra", "opus", "large", "70b", "120b", "550b", "max", "sol"}
# Kept under the old name for anything that still imports it.
_CHEAP_KEYWORDS = sorted(_CHEAP_MID | _CHEAP_LOW)

# Model families that are not general chat/tool-calling models. Real example from a user's cached
# Gemini list: "deep-research-max-preview-04-2026" matched the "max" keyword and would have been
# picked for every complex request -- a research-agent model, not a chat model. The list-time
# filter (_NON_CHAT_DENYLIST) only removes obviously non-chat entries, so these get through it.
_SPECIAL_PURPOSE_TOKENS = {
    "research", "antigravity", "computer", "robotics", "lyria", "banana", "customtools", "codex",
    "realtime", "transcribe", "live", "imagen", "veo", "learnlm", "search", "guard", "embedding",
}
_UNSTABLE_TOKENS = {"preview", "exp", "experimental", "beta"}


def _tokens(model_id):
    return [t for t in re.split(r"[^a-z0-9]+", (model_id or "").lower()) if t]


def is_special_purpose(model_id):
    return bool(set(_tokens(model_id)) & _SPECIAL_PURPOSE_TOKENS)


def is_cheap_tier(model_id):
    """True if the name says this is already a small/cheap model."""
    return bool(set(_tokens(model_id)) & (_CHEAP_MID | _CHEAP_LOW))


def _version(model_id):
    m = re.search(r"\d+(?:\.\d+)*", model_id or "")
    return tuple(int(x) for x in m.group(0).split(".")) if m else ()


def _tier_score(tokens, complexity):
    toks = set(tokens)
    if complexity == "simple":
        mid, low = len(toks & _CHEAP_MID), len(toks & _CHEAP_LOW)
        # "flash-lite" must rank below plain "flash": the cheapest tier is the least reliable at
        # picking the right tool out of ~180, and a wrong pick costs a whole extra turn.
        return mid * 10 + (low if not mid else -low)
    return len(toks & _CAPABLE_KEYWORDS)


def classify_complexity(query: str) -> str:
    """Deterministic heuristic, not ML: word count, multi-step phrasing,
    quantity words, and how many distinct GIS operations are named. Good
    enough to route between two tiers; not a promise of perfect complexity
    detection. A single GIS term ("list layers") is not treated as complex on
    its own -- it takes an explicit multi-step signal or several distinct
    operations to tip a request into the "complex" tier.

    Previously also forced "complex" once conversation_history exceeded 6
    messages -- but history grows by 2 per turn, so that tripped after only
    3-4 exchanges and then stayed tripped for the rest of the session
    regardless of what was actually being asked ("zoom to that layer" got
    routed to the expensive tier identically to a genuine multi-step
    analysis). Dropped: the content signals above are already meaningful on
    their own and don't need a session-length proxy on top."""
    if not query:
        return "simple"

    q = query.lower()
    word_count = len(query.split())
    has_multi_step_phrase = any(p in q for p in _MULTI_STEP_PHRASES)
    has_quantity_signal = any(p in q for p in _QUANTITY_SIGNALS)
    distinct_operations = sum(1 for v in _OPERATION_VERBS if v in q)

    if (
        word_count > 40
        or has_multi_step_phrase
        or has_quantity_signal
        or distinct_operations >= 2
    ):
        return "complex"
    return "simple"


def pick_model_for_complexity(model_ids, complexity: str) -> str:
    """Scores model IDs by naming convention and returns the best match for the
    requested tier, or "" when there is nothing suitable to pick. Only ever returns an
    entry already present in model_ids -- never fabricates a new model name.

    Special-purpose models (deep-research, robotics, music, ...) are never candidates, without
    exception: if every model in the list is special-purpose this returns "" and the caller keeps
    its known-safe default. ("Don't optimise" beats picking a model this module has classified as
    unsuitable -- e.g. "nano-banana-pro-preview" carries the cheap token "nano".)

    Ties are broken, in order, by: not a preview/experimental model, then a "-latest" alias, then
    the highest version number. Stability comes before "latest" because a name containing
    "latest" says nothing about whether the model behind it is stable."""
    usable = [m for m in (model_ids or []) if not is_special_purpose(m)]
    if not usable:
        return ""

    scored = []
    for model_id in usable:
        toks = _tokens(model_id)
        rank = (
            _tier_score(toks, complexity),
            0 if set(toks) & _UNSTABLE_TOKENS else 1,
            1 if "latest" in toks else 0,
            _version(model_id),
        )
        scored.append((rank, model_id))

    best_rank, best_model = max(scored, key=lambda pair: pair[0])
    if best_rank[0] > 0:
        return best_model

    # No naming signal found for either tier -- string length isn't a
    # reliable proxy for model size/cost (a "-mini"/"-nano" suffix would
    # already have scored above; a model with truly no naming signal at all
    # gives no honest basis to guess "smaller" from a shorter string), so both
    # tiers fall back to the same predictable choice -- the first entry in the
    # list -- rather than "simple" pretending to a precision it doesn't have.
    return usable[0]
