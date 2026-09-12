# -*- coding: utf-8 -*-
import unittest
from cartogen_ai.core.ui.chat_formatting import (
    render_markdown, _relative_time, _blend_hex, derive_bubble_colors,
    escape_plain_text, now_iso, friendly_tool_name, render_tool_step_html,
    build_dock_stylesheet, format_send_error, _brand_accent, BRAND_TEAL, BRAND_ACCENT_BLEND_T,
)


class TestFormatSendError(unittest.TestCase):
    """Regression coverage for the UX audit (2026-08-31) finding that every
    send error reached the user as raw exception text with no indication of
    what to do about it."""

    def test_401_gets_auth_hint(self):
        msg = format_send_error("401 Client Error: Unauthorized for url: https://openrouter.ai/api/v1/chat/completions")
        self.assertIn("authentication problem", msg)
        self.assertIn("Settings", msg)

    def test_429_gets_rate_limit_hint(self):
        msg = format_send_error("429 Too Many Requests")
        self.assertIn("Rate limited", msg)

    def test_connection_error_gets_network_hint(self):
        msg = format_send_error("ConnectionError: Failed to establish a new connection: [Errno 111] Connection refused")
        self.assertIn("Couldn't reach the provider", msg)

    def test_unclassified_error_falls_back_to_raw_text(self):
        msg = format_send_error("some never-seen-before provider error")
        self.assertIn("**Error:**", msg)
        self.assertIn("some never-seen-before provider error", msg)

    def test_original_detail_is_never_hidden_even_when_classified(self):
        # Classification is a hint layered on top, never a replacement --
        # the raw detail must always still be present for debugging.
        raw = "401 Client Error: Unauthorized for url: https://example.test/v1"
        msg = format_send_error(raw)
        self.assertIn(raw, msg)

    def test_empty_error_does_not_crash(self):
        msg = format_send_error("")
        self.assertIsInstance(msg, str)
        self.assertIn("no error detail", msg)


class TestRenderMarkdown(unittest.TestCase):
    def test_headers(self):
        self.assertIn('font-size:15px', render_markdown("# Title"))
        self.assertIn('font-size:13.5px', render_markdown("### Sub"))

    def test_bold_and_strikethrough(self):
        html = render_markdown("**bold** and ~~gone~~")
        self.assertIn("<b>bold</b>", html)
        self.assertIn("<s>gone</s>", html)

    def test_inline_code_and_fenced_block(self):
        html = render_markdown("use `x = 1` then:\n```python\ny = 2\n```")
        self.assertIn("<code", html)
        self.assertIn("<pre", html)
        self.assertIn("y = 2", html)

    def test_gfm_table(self):
        html = render_markdown("| Name | Count |\n|---|---|\n| A | 1 |\n| B | 2 |")
        self.assertIn("<table", html)
        self.assertIn("<th", html)
        self.assertIn(">Name<", html)
        self.assertIn(">A<", html)
        self.assertIn(">2<", html)

    def test_non_table_pipe_text_not_mistaken_for_table(self):
        # A single line with pipes but no valid separator row must NOT be
        # rendered as a table.
        html = render_markdown("value | other value")
        self.assertNotIn("<table", html)

    def test_blockquote_groups_consecutive_lines(self):
        html = render_markdown("> first line\n> second line")
        self.assertEqual(html.count("<div style=\"border-left"), 1)
        self.assertIn("first line", html)
        self.assertIn("second line", html)

    def test_nested_bullets_indent_further_than_top_level(self):
        html = render_markdown("- top\n  - nested")
        lines = html.split("<br>")
        top_line = next(l for l in lines if "top" in l)
        nested_line = next(l for l in lines if "nested" in l)
        self.assertGreater(nested_line.count("&nbsp;"), top_line.count("&nbsp;"))

    def test_numbered_list(self):
        html = render_markdown("1. first\n2. second")
        self.assertIn("1. first", html)
        self.assertIn("2. second", html)

    def test_link(self):
        html = render_markdown("[QGIS](https://qgis.org)")
        self.assertIn('<a href="https://qgis.org">QGIS</a>', html)

    def test_html_special_characters_are_escaped_outside_code(self):
        html = render_markdown("value < 5 & > 10")
        self.assertIn("&lt;", html)
        self.assertIn("&amp;", html)
        self.assertIn("&gt;", html)

    def test_default_colors_used_when_none_supplied(self):
        # Locks in the pre-existing static fallback (matches derive_bubble_colors'
        # own no-palette fallback) so a bare render_markdown(text) call -- as used
        # by any caller that hasn't been updated to pass live theme colors -- still
        # renders deterministically: the code chip background is derived from that
        # fallback's agent_bg/text (via _blend_hex), and the text color matches
        # the fallback's "text" entry exactly.
        html = render_markdown("`x = 1`")
        expected_bg = _blend_hex("#eef0f2", "#1c1c1c", 0.15)
        self.assertIn(f"background-color: {expected_bg}", html)
        self.assertIn("color: #1c1c1c", html)

    def test_dark_theme_colors_flow_into_code_and_table_and_blockquote(self):
        # Regression test for a real bug: code blocks, inline code, table
        # borders/text, <hr>, and blockquotes were hardcoded to fixed
        # light-theme colors regardless of the live QGIS theme, making code
        # blocks in particular unreadable in a dark theme (light-grey
        # background, no matching foreground color). render_markdown must
        # follow the same colors dict derive_bubble_colors() produces.
        dark_colors = {
            "user_bg": "#2a2a2a", "agent_bg": "#333333", "text": "#e0e0e0",
            "subtle": "#a0a0a0", "border": "#555555",
        }
        inline_html = render_markdown("use `x = 1` here", dark_colors)
        self.assertIn("#e0e0e0", inline_html)  # code text is readable against a dark bubble
        self.assertNotIn("#e8e8e8", inline_html)  # the old fixed light-grey chip is gone

        block_html = render_markdown("```python\ny = 2\n```", dark_colors)
        self.assertIn("#e0e0e0", block_html)
        self.assertNotIn("#e8e8e8", block_html)

        table_html = render_markdown("| A | B |\n|---|---|\n| 1 | 2 |", dark_colors)
        self.assertIn("#555555", table_html)
        self.assertIn("#e0e0e0", table_html)

        quote_html = render_markdown("> quoted", dark_colors)
        self.assertIn("#a0a0a0", quote_html)  # subtle/muted color, not the old fixed #666
        self.assertNotIn("color:#666", quote_html)

        hr_html = render_markdown("---", dark_colors)
        self.assertIn("#555555", hr_html)


class TestRelativeTime(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(_relative_time(""), "")
        self.assertEqual(_relative_time(None), "")

    def test_unparseable_input_degrades_gracefully(self):
        self.assertEqual(_relative_time("not-a-date"), "")

    def test_just_now(self):
        self.assertEqual(_relative_time(now_iso()), "just now")


class TestBlendHex(unittest.TestCase):
    def test_endpoints(self):
        self.assertEqual(_blend_hex("#000000", "#ffffff", 0.0), "#000000")
        self.assertEqual(_blend_hex("#000000", "#ffffff", 1.0), "#ffffff")

    def test_midpoint(self):
        self.assertEqual(_blend_hex("#000000", "#ffffff", 0.5), "#808080")


class TestDeriveBubbleColors(unittest.TestCase):
    def test_no_palette_returns_static_fallback(self):
        colors = derive_bubble_colors(None)
        self.assertEqual(colors["user_bg"], "#dce8f7")
        self.assertIn("agent_bg", colors)
        self.assertIn("accent", colors)  # the fallback dict has it too, not just the live-palette path

    def test_uses_theme_values_when_given(self):
        palette = {
            "window": "#202020", "alt_base": "#282828", "text": "#e0e0e0",
            "highlight": "#3daee9", "muted_text": "#909090", "mid": "#404040",
        }
        colors = derive_bubble_colors(palette)
        self.assertEqual(colors["agent_bg"], "#282828")
        self.assertEqual(colors["text"], "#e0e0e0")
        self.assertEqual(colors["subtle"], "#909090")
        # user_bg should be a blend of window and highlight, not either raw value
        self.assertNotIn(colors["user_bg"], (palette["window"], palette["highlight"]))

    def test_accent_is_the_brand_blended_highlight_not_the_raw_one(self):
        # UI real-session-feedback fixes (2026-09-12): "accent" is exposed for the chat
        # bubble's left-accent stripe -- must be the same brand-blended value user_bg's own
        # blend uses, not the raw QGIS highlight color.
        palette = {"window": "#f0f0f0", "highlight": "#3daee9"}
        colors = derive_bubble_colors(palette)
        self.assertEqual(colors["accent"], _brand_accent(palette["highlight"]))
        self.assertNotEqual(colors["accent"], palette["highlight"])


class TestEscapePlainText(unittest.TestCase):
    def test_escapes_html_and_preserves_newlines_as_br(self):
        result = escape_plain_text("a < b\nsecond line")
        self.assertIn("&lt;", result)
        self.assertIn("<br>", result)
        self.assertNotIn("\n", result)


class TestFriendlyToolName(unittest.TestCase):
    def test_converts_snake_case_to_capitalized_phrase(self):
        self.assertEqual(friendly_tool_name("apply_graduated_style"), "Apply graduated style")
        self.assertEqual(friendly_tool_name("get_layers"), "Get layers")

    def test_single_word_capitalized(self):
        self.assertEqual(friendly_tool_name("buffer"), "Buffer")

    def test_empty_name_has_a_fallback(self):
        self.assertEqual(friendly_tool_name(""), "tool")
        self.assertEqual(friendly_tool_name(None), "tool")


class TestRenderToolStepHtml(unittest.TestCase):
    _colors = {"subtle": "#888888", "text": "#222222"}

    def test_running_status_shows_using_label(self):
        html = render_tool_step_html("apply_graduated_style", "running", None, self._colors)
        self.assertIn("Using Apply graduated style", html)
        self.assertIn("#888888", html)

    def test_done_status_shows_used_label(self):
        html = render_tool_step_html("get_layers", "done", None, self._colors)
        self.assertIn("Used Get layers", html)

    def test_failed_status_includes_error_text(self):
        html = render_tool_step_html("buffer_analysis", "failed", "Layer not found", self._colors)
        self.assertIn("Failed: Buffer analysis", html)
        self.assertIn("Layer not found", html)
        self.assertIn("#222222", html)  # uses the "text" color key, not "subtle", for visibility

    def test_error_text_is_html_escaped(self):
        html = render_tool_step_html("buffer_analysis", "failed", "<script>evil</script>", self._colors)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_no_error_text_appended_when_error_is_none(self):
        html = render_tool_step_html("buffer_analysis", "failed", None, self._colors)
        self.assertIn("Failed: Buffer analysis", html)
        self.assertNotIn("&mdash;", html)

    def test_unknown_status_falls_back_to_running_style(self):
        html = render_tool_step_html("get_layers", "bogus_status", None, self._colors)
        self.assertIn("Using Get layers", html)


class TestBrandAccent(unittest.TestCase):
    """UI/chat redesign workstream (2026-09-12): the one place this module's colors pick up
    Cartogen brand identity -- blending QGIS's own live accent color toward the brand teal,
    deliberately never replacing it outright, so the result still varies across QGIS themes
    instead of becoming one fixed color that could clash with an unexpected theme."""

    def test_blends_toward_brand_teal_not_replacing_it(self):
        result = _brand_accent("#3daee9")
        self.assertNotEqual(result, "#3daee9")  # actually blended, not a no-op
        self.assertNotEqual(result, BRAND_TEAL)  # blended, not fully replaced

    def test_matches_blend_hex_at_the_documented_ratio(self):
        highlight = "#3daee9"
        self.assertEqual(_brand_accent(highlight), _blend_hex(highlight, BRAND_TEAL, BRAND_ACCENT_BLEND_T))

    def test_is_deterministic(self):
        self.assertEqual(_brand_accent("#3daee9"), _brand_accent("#3daee9"))

    def test_different_qgis_themes_still_produce_different_accents(self):
        # The whole point of blending rather than replacing: two different QGIS highlight
        # colors must still produce two different brand-blended results, not collapse to one
        # fixed brand color regardless of theme.
        light_theme_accent = _brand_accent("#3daee9")
        dark_theme_accent = _brand_accent("#8ab4f8")
        self.assertNotEqual(light_theme_accent, dark_theme_accent)


class TestDeriveBubbleColorsBrandAccent(unittest.TestCase):
    def test_user_bg_reflects_brand_blended_highlight(self):
        window = "#f0f0f0"
        raw_highlight = "#3daee9"
        colors = derive_bubble_colors({"window": window, "highlight": raw_highlight})
        # user_bg is window blended 22% toward the BRAND-blended highlight, not the raw one --
        # confirm it differs from what the old (pre-brand-accent) blend would have produced.
        old_behavior_bg = _blend_hex(window, raw_highlight, 0.22)
        self.assertNotEqual(colors["user_bg"], old_behavior_bg)
        expected_bg = _blend_hex(window, _brand_accent(raw_highlight), 0.22)
        self.assertEqual(colors["user_bg"], expected_bg)


class TestBuildDockStylesheet(unittest.TestCase):
    def test_falls_back_to_defaults_when_no_palette(self):
        qss = build_dock_stylesheet(None)
        self.assertIn("QPushButton", qss)
        # The default highlight fallback (#3daee9) is now blended toward the Cartogen brand
        # teal (_brand_accent, UI/chat redesign workstream, 2026-09-12) rather than appearing
        # bare -- #329cbd is that blend's exact, deterministic output.
        self.assertIn("#329cbd", qss)

    def test_uses_given_palette_colors(self):
        qss = build_dock_stylesheet({
            "window": "#2b2b2b", "base": "#1e1e1e", "alt_base": "#333333",
            "text": "#e0e0e0", "muted_text": "#909090", "mid": "#555555",
            "highlight": "#3daee9", "highlighted_text": "#ffffff",
        })
        self.assertIn("#2b2b2b", qss)
        self.assertIn("#e0e0e0", qss)

    def test_defines_expected_object_name_variants(self):
        qss = build_dock_stylesheet(None)
        for object_name in ("secondaryButton", "dangerButton", "successButton", "chipButton"):
            self.assertIn(f"#{object_name}", qss)

    def test_is_deterministic_for_the_same_input(self):
        palette = {"window": "#ffffff", "highlight": "#123456"}
        self.assertEqual(build_dock_stylesheet(palette), build_dock_stylesheet(palette))


if __name__ == "__main__":
    unittest.main()
