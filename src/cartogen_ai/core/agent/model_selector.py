# -*- coding: utf-8 -*-
"""
Complexity-based automatic model selection for Cartogen AI.
Picks between a cheaper/faster and a more capable model from whatever live
model list a provider actually returned -- never invents a model ID.
"""

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

_CHEAP_KEYWORDS = ["nano", "mini", "lite", "flash", "8b", "9b", "12b", "20b", "small", "haiku", "instant"]
_CAPABLE_KEYWORDS = ["pro", "ultra", "opus", "large", "70b", "120b", "550b", "max", "sol"]


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
    requested tier. Only ever returns an entry already present in model_ids --
    never fabricates a new model name."""
    if not model_ids:
        return ""

    keywords = _CHEAP_KEYWORDS if complexity == "simple" else _CAPABLE_KEYWORDS
    scored = []
    for model_id in model_ids:
        lower = model_id.lower()
        score = sum(1 for kw in keywords if kw in lower)
        scored.append((score, model_id))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    best_score, best_model = scored[0]
    if best_score > 0:
        return best_model

    # No naming signal found for either tier -- string length isn't a
    # reliable proxy for model size/cost (a "-mini"/"-nano" suffix would
    # already have scored above via _CHEAP_KEYWORDS; a model with truly no
    # naming signal at all gives no honest basis to guess "smaller" from a
    # shorter string), so both tiers fall back to the same predictable
    # choice -- the first entry in the list -- rather than "simple"
    # pretending to a precision it doesn't have.
    return model_ids[0]
