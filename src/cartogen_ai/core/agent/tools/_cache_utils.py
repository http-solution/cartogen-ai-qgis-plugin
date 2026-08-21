# -*- coding: utf-8 -*-
"""
Small shared in-memory TTL cache for repeated identical external lookups
within a plugin session (geocoding, OSM, HDX, geoBoundaries). Mirrors the
cache pattern already proven in multimodal_remote_sensing.py's _STAC_CACHE --
formalized here since several tool modules now need the identical behavior.
Plugin-process-lifetime scoping, same as every other module-global cache in
this codebase -- resets naturally on plugin reload/QGIS restart.
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
