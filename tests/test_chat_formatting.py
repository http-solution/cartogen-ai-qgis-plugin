# -*- coding: utf-8 -*-
import unittest
from ui.chat_formatting import (
    render_markdown, _relative_time, _blend_hex, derive_bubble_colors,
    escape_plain_text, now_iso, friendly_tool_name, render_tool_step_html,
    build_dock_stylesheet,
)


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


class TestBuildDockStylesheet(unittest.TestCase):
    def test_falls_back_to_defaults_when_no_palette(self):
        qss = build_dock_stylesheet(None)
        self.assertIn("QPushButton", qss)
        self.assertIn("#3daee9", qss)  # default highlight fallback

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
