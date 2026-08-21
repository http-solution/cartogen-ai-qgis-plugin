# -*- coding: utf-8 -*-
import unittest
from cartogen_ai.core.agent.model_selector import classify_complexity, pick_model_for_complexity, filter_chat_model_ids


class TestClassifyComplexity(unittest.TestCase):
    def test_short_query_is_simple(self):
        self.assertEqual(classify_complexity("list layers"), "simple")

    def test_greeting_is_simple(self):
        self.assertEqual(classify_complexity("hi"), "simple")

    def test_multi_step_query_is_complex(self):
        query = "Buffer this layer by 500m, then intersect it with the flood zone, and join the results"
        self.assertEqual(classify_complexity(query), "complex")

    def test_long_query_is_complex(self):
        query = " ".join(["word"] * 45)
        self.assertEqual(classify_complexity(query), "complex")

    def test_short_query_stays_simple_regardless_of_history(self):
        # history_len was dropped as a signal entirely -- it used to force
        # "complex" after only 3-4 exchanges (history grows by 2/turn),
        # permanently defeating auto-routing for any sustained conversation
        # regardless of what was actually being asked.
        self.assertEqual(classify_complexity("ok now do the next one"), "simple")

    def test_empty_query_is_simple(self):
        self.assertEqual(classify_complexity(""), "simple")


class TestPickModelForComplexity(unittest.TestCase):
    def test_picks_cheap_model_for_simple(self):
        models = ["provider/big-pro-70b", "provider/small-flash-8b"]
        self.assertEqual(pick_model_for_complexity(models, "simple"), "provider/small-flash-8b")

    def test_picks_capable_model_for_complex(self):
        models = ["provider/small-flash-8b", "provider/big-ultra-120b"]
        self.assertEqual(pick_model_for_complexity(models, "complex"), "provider/big-ultra-120b")

    def test_empty_list_returns_empty_string(self):
        self.assertEqual(pick_model_for_complexity([], "simple"), "")

    def test_no_naming_signal_falls_back_to_first_entry_for_both_tiers(self):
        # "simple" used to fall back to the shortest model NAME as a proxy
        # for "smaller/base variant" -- but string length isn't a reliable
        # signal of model size/cost, so this deliberately puts the shorter
        # name SECOND to prove the fallback no longer follows it.
        models = ["custom-model-first", "x"]
        self.assertEqual(pick_model_for_complexity(models, "simple"), "custom-model-first")
        self.assertEqual(pick_model_for_complexity(models, "complex"), "custom-model-first")

    def test_never_returns_a_model_not_in_the_input_list(self):
        models = ["only-option-here"]
        self.assertEqual(pick_model_for_complexity(models, "simple"), "only-option-here")
        self.assertEqual(pick_model_for_complexity(models, "complex"), "only-option-here")


class TestFilterChatModelIds(unittest.TestCase):
    def test_drops_non_chat_models(self):
        ids = ["gpt-5.6", "text-embedding-3-large", "whisper-1", "dall-e-3", "gpt-oss-20b"]
        filtered = filter_chat_model_ids(ids)
        self.assertIn("gpt-5.6", filtered)
        self.assertIn("gpt-oss-20b", filtered)
        self.assertNotIn("text-embedding-3-large", filtered)
        self.assertNotIn("whisper-1", filtered)
        self.assertNotIn("dall-e-3", filtered)

    def test_deduplicates_and_sorts(self):
        self.assertEqual(filter_chat_model_ids(["b-model", "a-model", "b-model"]), ["a-model", "b-model"])


if __name__ == "__main__":
    unittest.main()
