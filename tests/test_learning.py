# -*- coding: utf-8 -*-
"""Tests for agent/learning.py -- the adaptive self-learning helpers added
2026-09-02 (see BUG_TRACKER.md and learning.py's module docstring for the
feature request and the deliberate scoping of each mechanism).

SpatialMemoryManager's global notes are QgsSettings-backed only when
QGIS_AVAILABLE is True; outside a real QGIS process (as here) they live
purely in the manager's own in-memory dict for the lifetime of the instance,
so these tests never touch any real persisted state -- a fresh
SpatialMemoryManager() per test is a clean slate for global notes."""
import unittest

from cartogen_ai.core.agent.memory import SpatialMemoryManager
from cartogen_ai.core.agent import learning


class TestUsageTracking(unittest.TestCase):
    """Mechanism 3: usage-pattern-driven counters."""

    def test_record_tool_usage_increments(self):
        memory = SpatialMemoryManager()
        learning.record_tool_usage(memory, "create_buffer")
        learning.record_tool_usage(memory, "create_buffer")
        learning.record_tool_usage(memory, "apply_graduated_style")
        counts = learning.get_usage_counts(memory, learning.USAGE_TOOL_PREFIX)
        self.assertEqual(counts, {"create_buffer": 2, "apply_graduated_style": 1})

    def test_record_tool_usage_ignores_empty_name(self):
        memory = SpatialMemoryManager()
        learning.record_tool_usage(memory, "")
        learning.record_tool_usage(memory, None)
        self.assertEqual(learning.get_usage_counts(memory, learning.USAGE_TOOL_PREFIX), {})

    def test_record_provider_usage_increments(self):
        memory = SpatialMemoryManager()
        for _ in range(3):
            learning.record_provider_usage(memory, "openrouter")
        learning.record_provider_usage(memory, "gemini")
        counts = learning.get_usage_counts(memory, learning.USAGE_PROVIDER_PREFIX)
        self.assertEqual(counts, {"openrouter": 3, "gemini": 1})

    def test_usage_counts_survive_non_numeric_junk(self):
        memory = SpatialMemoryManager()
        memory.store_global_note(f"{learning.USAGE_TOOL_PREFIX}broken", "not-a-number")
        learning.record_tool_usage(memory, "create_buffer")
        counts = learning.get_usage_counts(memory, learning.USAGE_TOOL_PREFIX)
        self.assertEqual(counts, {"create_buffer": 1})


class TestPreferenceInference(unittest.TestCase):
    """Mechanism 1: passive preference detection, scoped to provider choice
    (see learning.py's module docstring for why that's the deliberately
    narrow first signal)."""

    def test_no_preference_below_minimum_sample_count(self):
        memory = SpatialMemoryManager()
        for _ in range(learning._PREFERENCE_MIN_SAMPLES - 1):
            learning.record_provider_usage(memory, "openrouter")
        learning.maybe_infer_preferences(memory)
        self.assertNotIn(f"{learning.PREF_PREFIX}preferred_provider", memory.get_global_notes())

    def test_no_preference_when_share_not_dominant(self):
        memory = SpatialMemoryManager()
        # 3 openrouter / 3 gemini -- 50/50, nowhere near the 70% threshold.
        for _ in range(3):
            learning.record_provider_usage(memory, "openrouter")
            learning.record_provider_usage(memory, "gemini")
        learning.maybe_infer_preferences(memory)
        self.assertNotIn(f"{learning.PREF_PREFIX}preferred_provider", memory.get_global_notes())

    def test_preference_inferred_once_dominant_and_enough_samples(self):
        memory = SpatialMemoryManager()
        for _ in range(6):
            learning.record_provider_usage(memory, "openrouter")
        learning.record_provider_usage(memory, "gemini")
        learning.maybe_infer_preferences(memory)
        value = memory.get_global_notes().get(f"{learning.PREF_PREFIX}preferred_provider")
        self.assertIsNotNone(value)
        self.assertIn("openrouter", value)
        self.assertIn("6/7", value)

    def test_maybe_infer_preferences_is_idempotent(self):
        memory = SpatialMemoryManager()
        for _ in range(5):
            learning.record_provider_usage(memory, "openrouter")
        learning.maybe_infer_preferences(memory)
        first = memory.get_global_notes()[f"{learning.PREF_PREFIX}preferred_provider"]
        learning.maybe_infer_preferences(memory)
        second = memory.get_global_notes()[f"{learning.PREF_PREFIX}preferred_provider"]
        self.assertEqual(first, second)


class TestCorrectionDetection(unittest.TestCase):
    """Mechanism 2: plain-text correction heuristic. Deliberately a starting
    heuristic, not a verified classifier -- see learning.py's module
    docstring for the honest false-positive/false-negative caveat. These
    cases just pin down today's behavior so a future change to the pattern
    list is a visible, deliberate decision."""

    def test_detects_common_correction_phrasings(self):
        positives = [
            "That's wrong, please use a different color ramp",
            "no, that's not what I asked for",
            "Actually I meant the 2023 data, not 2024",
            "undo that",
            "Please redo this with EPSG:4326",
            "Don't do that again",
            "No. Use the other provider.",
            "instead of buffers, please use a 1km grid",
        ]
        for msg in positives:
            with self.subTest(msg=msg):
                self.assertTrue(learning.detect_correction(msg))

    def test_does_not_flag_ordinary_requests(self):
        negatives = [
            "Can you add another layer for schools?",
            "What's the population of Aden in 2020?",
            "Create a 500m buffer around the river",
            "",
            None,
        ]
        for msg in negatives:
            with self.subTest(msg=msg):
                self.assertFalse(learning.detect_correction(msg))

    def test_record_correction_rule_stores_and_increments_index(self):
        memory = SpatialMemoryManager()
        key1 = learning.record_correction_rule(
            memory, "That's wrong, wrong color", "apply_graduated_style", {"field": "pop"}
        )
        key2 = learning.record_correction_rule(
            memory, "no, undo that", "create_buffer", {"distance": 500}
        )
        self.assertEqual(key1, "rule:1")
        self.assertEqual(key2, "rule:2")
        notes = memory.get_global_notes()
        self.assertIn("apply_graduated_style", notes[key1])
        self.assertIn("create_buffer", notes[key2])

    def test_record_correction_rule_without_last_tool(self):
        memory = SpatialMemoryManager()
        key = learning.record_correction_rule(memory, "no, that's wrong", None, None)
        self.assertIn("previous turn", memory.get_global_notes()[key])

    def test_record_correction_rule_truncates_long_excerpt(self):
        memory = SpatialMemoryManager()
        long_message = "no, " + "x" * 300
        key = learning.record_correction_rule(memory, long_message, "create_buffer", {})
        stored = memory.get_global_notes()[key]
        self.assertIn("...", stored)
        self.assertLess(len(stored), len(long_message) + 200)


class TestMemoryContextIntegration(unittest.TestCase):
    """The formatted context is what actually reaches the model and the
    memory panel -- confirms learning.py's writes show up correctly
    categorized (see memory.get_formatted_memory_context)."""

    def test_learned_data_appears_under_correct_headings(self):
        memory = SpatialMemoryManager()
        for _ in range(6):
            learning.record_provider_usage(memory, "openrouter")
        learning.record_provider_usage(memory, "gemini")
        learning.maybe_infer_preferences(memory)
        learning.record_tool_usage(memory, "create_buffer")
        learning.record_correction_rule(memory, "that's wrong", "create_buffer", {"distance": 500})

        ctx = memory.get_formatted_memory_context()
        self.assertIn("### Learned Preferences", ctx)
        self.assertIn("### Correction Rules", ctx)
        self.assertIn("### Usage Patterns", ctx)
        self.assertIn("preferred_provider", ctx)
        self.assertIn("create_buffer", ctx)

    def test_delete_global_note_removes_from_context(self):
        memory = SpatialMemoryManager()
        memory.store_global_note("pref:preferred_provider", "openrouter (used in 6/6 recent sessions)")
        self.assertIn("Learned Preferences", memory.get_formatted_memory_context())
        result = memory.delete_global_note("pref:preferred_provider")
        self.assertTrue(result["success"])
        self.assertTrue(result["existed"])
        self.assertNotIn("Learned Preferences", memory.get_formatted_memory_context())

    def test_delete_global_note_missing_key_reports_not_existed(self):
        memory = SpatialMemoryManager()
        result = memory.delete_global_note("pref:nonexistent")
        self.assertTrue(result["success"])
        self.assertFalse(result["existed"])

    def test_uncategorized_legacy_notes_still_render(self):
        memory = SpatialMemoryManager()
        memory.store_global_note("preferred_unit", "meters")
        ctx = memory.get_formatted_memory_context()
        self.assertIn("### User Global Preferences:", ctx)
        self.assertIn("preferred_unit", ctx)


if __name__ == "__main__":
    unittest.main()
