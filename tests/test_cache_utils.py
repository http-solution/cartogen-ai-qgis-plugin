# -*- coding: utf-8 -*-
"""Tests for agent/tools/_cache_utils.py's TTLCache, including the on_evict callback
added for SEC-004 (2026-09-14 audit) -- see humanitarian_tools.py's
_cleanup_cached_local_path for the real-world motivation (cleaning up a cached fetch
result's leftover temp file once the cache entry itself expires or is overwritten)."""
import time
import unittest
from unittest.mock import patch

from cartogen_ai.core.agent.tools._cache_utils import TTLCache


class TestTTLCacheBasics(unittest.TestCase):
    def test_set_then_get_returns_the_value(self):
        cache = TTLCache(ttl_seconds=100)
        cache.set("k", "v")
        self.assertEqual(cache.get("k"), "v")

    def test_get_missing_key_returns_none(self):
        cache = TTLCache(ttl_seconds=100)
        self.assertIsNone(cache.get("missing"))

    def test_expired_entry_returns_none(self):
        cache = TTLCache(ttl_seconds=100)
        with patch("cartogen_ai.core.agent.tools._cache_utils.time.time", return_value=1000.0):
            cache.set("k", "v")
        with patch("cartogen_ai.core.agent.tools._cache_utils.time.time", return_value=1101.0):
            self.assertIsNone(cache.get("k"))


class TestTTLCacheOnEvict(unittest.TestCase):
    def test_no_callback_by_default_is_a_safe_no_op(self):
        # Every existing caller before SEC-004 omits on_evict -- must stay unaffected.
        cache = TTLCache(ttl_seconds=100)
        with patch("cartogen_ai.core.agent.tools._cache_utils.time.time", return_value=1000.0):
            cache.set("k", "v")
        with patch("cartogen_ai.core.agent.tools._cache_utils.time.time", return_value=1101.0):
            self.assertIsNone(cache.get("k"))  # must not raise with no callback set

    def test_fires_on_natural_expiry(self):
        evicted = []
        cache = TTLCache(ttl_seconds=100, on_evict=lambda k, v: evicted.append((k, v)))
        with patch("cartogen_ai.core.agent.tools._cache_utils.time.time", return_value=1000.0):
            cache.set("k", "v")
        self.assertEqual(evicted, [])  # not evicted yet -- still fresh
        with patch("cartogen_ai.core.agent.tools._cache_utils.time.time", return_value=1101.0):
            cache.get("k")
        self.assertEqual(evicted, [("k", "v")])

    def test_does_not_fire_for_a_still_fresh_read(self):
        evicted = []
        cache = TTLCache(ttl_seconds=100, on_evict=lambda k, v: evicted.append((k, v)))
        cache.set("k", "v")
        cache.get("k")
        self.assertEqual(evicted, [])

    def test_fires_when_set_overwrites_an_existing_key(self):
        evicted = []
        cache = TTLCache(ttl_seconds=100, on_evict=lambda k, v: evicted.append((k, v)))
        cache.set("k", "old")
        cache.set("k", "new")
        self.assertEqual(evicted, [("k", "old")])
        self.assertEqual(cache.get("k"), "new")

    def test_does_not_fire_on_first_set_of_a_new_key(self):
        evicted = []
        cache = TTLCache(ttl_seconds=100, on_evict=lambda k, v: evicted.append((k, v)))
        cache.set("k", "v")
        self.assertEqual(evicted, [])

    def test_callback_exception_is_swallowed_not_propagated(self):
        # Cleanup is best-effort -- a broken callback must never break the cache's own
        # read/write path.
        def boom(k, v):
            raise RuntimeError("cleanup failed")

        cache = TTLCache(ttl_seconds=100, on_evict=boom)
        with patch("cartogen_ai.core.agent.tools._cache_utils.time.time", return_value=1000.0):
            cache.set("k", "v")
        with patch("cartogen_ai.core.agent.tools._cache_utils.time.time", return_value=1101.0):
            self.assertIsNone(cache.get("k"))  # must not raise


if __name__ == "__main__":
    unittest.main()
