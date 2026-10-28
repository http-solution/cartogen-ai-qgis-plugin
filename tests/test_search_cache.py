"""Direct tests for infrastructure/providers/_search_cache.py (PLAN-040 audit finding 11): a cache that returns a stale grounded-search
answer, or fails to expire it, silently changes what the user is told."""
import unittest
from unittest import mock

from cartogen_ai.infrastructure.providers._search_cache import TTLCache

_TIME = "cartogen_ai.infrastructure.providers._search_cache.time.time"


class TestTTLCache(unittest.TestCase):
    def test_miss_returns_none(self):
        self.assertIsNone(TTLCache(60).get("k"))

    def test_hit_within_the_ttl(self):
        cache = TTLCache(60)
        with mock.patch(_TIME, return_value=1000.0):
            cache.set("k", {"answer": 1})
        with mock.patch(_TIME, return_value=1059.9):
            self.assertEqual(cache.get("k"), {"answer": 1})

    def test_expired_entry_is_dropped_and_returns_none(self):
        cache = TTLCache(60)
        with mock.patch(_TIME, return_value=1000.0):
            cache.set("k", "v")
        with mock.patch(_TIME, return_value=1060.0):  # exactly the TTL counts as expired
            self.assertIsNone(cache.get("k"))
        self.assertNotIn("k", cache._store)

    def test_set_overwrites_and_restarts_the_clock(self):
        cache = TTLCache(60)
        with mock.patch(_TIME, return_value=1000.0):
            cache.set("k", "old")
        with mock.patch(_TIME, return_value=1050.0):
            cache.set("k", "new")
        with mock.patch(_TIME, return_value=1100.0):
            self.assertEqual(cache.get("k"), "new")

    def test_falsy_values_are_cached_not_treated_as_misses_by_the_store(self):
        cache = TTLCache(60)
        cache.set("empty", "")
        self.assertEqual(cache.get("empty"), "")


if __name__ == "__main__":
    unittest.main()
