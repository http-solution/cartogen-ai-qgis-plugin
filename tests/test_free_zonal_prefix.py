"""_free_zonal_prefix: each damage run uses a zonal-statistics column prefix that is not on the layer yet (self-audit round 2, 2026-10-26)."""
import unittest
from unittest.mock import MagicMock

from cartogen_ai.core.agent.tools.analysis_tools import _free_zonal_prefix


def _layer(*names):
    layer = MagicMock()
    fields = []
    for n in names:
        f = MagicMock()
        f.name.return_value = n
        fields.append(f)
    layer.fields.return_value = fields
    return layer


class TestFreeZonalPrefix(unittest.TestCase):
    def test_unused_prefix_is_kept(self):
        self.assertEqual(_free_zonal_prefix(_layer("name"), "chg_"), "chg_")

    def test_a_taken_prefix_moves_on(self):
        self.assertEqual(_free_zonal_prefix(_layer("chg_mean"), "chg_"), "chg2_")
        self.assertEqual(_free_zonal_prefix(_layer("chg_mean", "chg2_mean"), "chg_"), "chg3_")
        self.assertEqual(_free_zonal_prefix(_layer("hzd_mean"), "hzd_"), "hzd2_")


if __name__ == "__main__":
    unittest.main()
