# -*- coding: utf-8 -*-
"""
Small shared in-memory TTL cache for the grounded-search provider calls
(gemini.py/openai.py's grounded_search()) -- both are real, billed LLM API
calls with no caching before this, unlike every "fetch external thing" tool
in agent/tools/ (see agent/tools/_cache_utils.py's TTLCache, which this
mirrors). Deliberately a standalone duplicate rather than importing that
same class: agent/tools/__init__.py eagerly imports all 14 tool modules to
populate the tool registry, and nothing in this codebase currently imports
across the providers/tools package boundary in either direction -- doing so
here risks a circular import for any test or code path that imports a
provider module before agent.tools has already been loaded. This class is
~15 dependency-free lines, cheap to keep in sync by inspection if the other
one ever changes.
"""

import time


class TTLCache:
    def __init__(self, ttl_seconds):
        self._ttl = ttl_seconds
        self._store = {}

    def get(self, key):
        entry = self._store.get(key)
        if entry is None:
            return None
        cached_at, value = entry
        if time.time() - cached_at >= self._ttl:
            del self._store[key]
            return None
        return value

    def set(self, key, value):
        self._store[key] = (time.time(), value)
