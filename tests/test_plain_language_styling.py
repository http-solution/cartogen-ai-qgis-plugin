"""Plain-language styling requests: colour words resolve, and everyday phrasing reaches a style tool.

The router cases are the measured gaps from the rc18 plain-language probe (before the aliases were added each of these
got no style tool, or only set_layer_order / set_layer_transparency). They pin that the right tool is a candidate; they do NOT
prove the model then picks it or draws a readable map -- that is what the live sheet's plain-language rows measure.
"""
import importlib
import pkgutil
import unittest

from cartogen_ai.core.agent.tools.plain_colour import resolve_colour


def _router():
    import cartogen_ai.core.agent.tools as tools
    for m in pkgutil.iter_modules(tools.__path__):
        try:
            importlib.import_module("cartogen_ai.core.agent.tools." + m.name)
        except Exception:
            pass
    from cartogen_ai.core.agent.tools.registry import get_tools_schema
    from cartogen_ai.core.services.tool_router import ToolRouter
    return ToolRouter(get_tools_schema())


def _names(router, query):
    return {(t.get("function") or t)["name"] for t in router.filter_relevant_tools(query)}


class ResolveColourTest(unittest.TestCase):
    def test_plain_words(self):
        for text in ("red", "dark red", "Pale-Yellow", "light blue", "deep green", "bright orange", "dark_grey"):
            self.assertRegex(resolve_colour(text), r"^#[0-9a-f]{6}$", text)

    def test_shades_order(self):
        def lum(h):
            return sum(int(h[i:i + 2], 16) for i in (1, 3, 5))
        self.assertLess(lum(resolve_colour("dark red")), lum(resolve_colour("red")))
        self.assertGreater(lum(resolve_colour("pale red")), lum(resolve_colour("light red")))
        self.assertGreater(lum(resolve_colour("light red")), lum(resolve_colour("red")))

    def test_hex_passes_through(self):
        self.assertEqual(resolve_colour("#AA00bb"), "#aa00bb")

    def test_unknown_returns_none(self):
        for text in ("", "shiny red", "dark", "lilac-ish", None, 5):
            self.assertIsNone(resolve_colour(text), text)


class PlainLanguageRoutingTest(unittest.TestCase):
    CASES = [
        ("Colour the districts by how many people live there", "apply_graduated_style"),
        ("Show where people are crowded together", "apply_heatmap_style"),
        ("Draw the bigger villages with bigger dots", "apply_graduated_symbol_style"),
        ("Put the names of the districts on the map", "apply_labels"),
        ("Make the zones see-through so I can see the points underneath", "set_layer_transparency"),
        ("Make the clinics stand out on the map", "change_layer_color"),
        ("Highlight the worst affected areas", "apply_humanitarian_look"),
        ("Make the map easier to read for a briefing", "auto_arrange_layer_order"),
    ]

    @classmethod
    def setUpClass(cls):
        cls.router = _router()

    def test_each_phrase_reaches_its_tool(self):
        for query, tool in self.CASES:
            self.assertIn(tool, _names(self.router, query), query)


if __name__ == "__main__":
    unittest.main()
