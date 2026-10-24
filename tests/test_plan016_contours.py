"""PLAN-016 item 4 (A18 of the first rc50 hand run): 'draw contour lines of the dem every 100' restyled the DEM (set_raster_relief) instead of
making contour lines (generate_contours). Offline we can check what the router OFFERS and that the two tool descriptions tell the model
which to pick; which one the model then picks is only checked by the owner's re-run of the row."""
import unittest

from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
from cartogen_ai.core.services.tool_router import ToolRouter

PROMPTS = ("draw contour lines of the dem every 100", "contour lines of the dem every 100 metres", "make contours from the dem",
           "create contour lines at 50 m interval", "draw contours of the elevation raster")


def _description(name):
    return next(t["function"]["description"] for t in TOOLS_SCHEMA if t["function"]["name"] == name)


class TestContourRouting(unittest.TestCase):
    def test_the_contour_maker_is_offered_for_every_phrasing(self):
        router = ToolRouter(TOOLS_SCHEMA)
        for prompt in PROMPTS:
            offered = [t["function"]["name"] for t in router.filter_relevant_tools(prompt)]
            self.assertIn("generate_contours", offered, prompt)

    def test_the_two_descriptions_point_at_each_other_with_the_deciding_cue(self):
        maker, styler = _description("generate_contours"), _description("set_raster_relief")
        self.assertIn("NEW LINE LAYER", maker)
        self.assertIn("draw / make / create contour lines", maker)
        self.assertIn("set_raster_relief", maker)
        self.assertIn("DISPLAYED", styler)
        self.assertIn("creates no layer and no file", styler)
        self.assertIn("generate_contours", styler)


if __name__ == "__main__":
    unittest.main()
