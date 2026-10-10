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
    def __init__(self, ttl_seconds, on_evict=None):
        """on_evict(key, value), if given, is called whenever a cached entry is discarded --
        naturally expiring in get(), or overwritten by a fresh set() for the same key. Optional
        and backward-compatible (every existing caller omits it, unaffected). Added for SEC-004
        (2026-09-14 audit): several humanitarian_tools.py cache entries carry a local temp-file
        path (deliberately kept alive while cached, so a repeat call within the TTL window reuses
        the already-downloaded file instead of re-fetching) that was never cleaned up once the
        cache entry itself expired -- a real, if low-severity, resource leak. A cleanup callback
        here lets a specific cache instance delete that file exactly when it stops being needed,
        without every other TTLCache user (which may cache plain data, nothing to clean up)
        having to know or care. Any exception from the callback is swallowed -- cleanup best-
        effort, must never break the cache's own read/write path."""
        self._ttl = ttl_seconds
        self._store = {}
        self._on_evict = on_evict

    def _fire_evict(self, key, value):
        if self._on_evict is None:
            return
        try:
            self._on_evict(key, value)
        except Exception:  # nosec B110 (best-effort: failure is non-fatal)
            pass

    def get(self, key):
        entry = self._store.get(key)
        if entry is None:
            return None
        cached_at, value = entry
        if time.time() - cached_at >= self._ttl:
            del self._store[key]
            self._fire_evict(key, value)
            return None
        return value

    def set(self, key, value):
        old_entry = self._store.get(key)
        self._store[key] = (time.time(), value)
        if old_entry is not None:
            _, old_value = old_entry
            if old_value is not value:
                self._fire_evict(key, old_value)
