"""PLAN-023 R3-1: spectral index formulas, hand-computed known answers (the numbers are worked out in the plan and in the comments here).
Pure numpy: skipped where numpy is missing (the CI test job installs it)."""
import unittest

try:
    import numpy as np
    HAVE_NUMPY = True
except ImportError:
    HAVE_NUMPY = False

from cartogen_ai.core.agent.tools import raster_indices as ri


def one(value):
    return np.array([[value]], dtype=np.float64)


def idx(index, valid=True, **bands):
    values, ok = ri.compute_index(index, {k: one(v) for k, v in bands.items()}, np.array([[valid]]))
    return float(values[0, 0]), bool(ok[0, 0])


@unittest.skipUnless(HAVE_NUMPY, "numpy not installed")
class TestKnownAnswers(unittest.TestCase):
    def test_savi(self):
        # SAVI(NIR 0.5, Red 0.1, L 0.5) = (0.5 - 0.1) / (0.5 + 0.1 + 0.5) x 1.5 = 0.4 / 1.1 x 1.5 = 0.545454...
        value, ok = idx("SAVI", nir=0.5, red=0.1)
        self.assertTrue(ok)
        self.assertAlmostEqual(value, 0.5455, places=4)

    def test_savi_with_another_soil_factor(self):
        # L = 0: SAVI reduces to NDVI = 0.4 / 0.6 = 0.6667
        value, _ok = ri.compute_index("SAVI", {"nir": one(0.5), "red": one(0.1)}, np.array([[True]]), soil_factor=0.0)
        self.assertAlmostEqual(float(value[0, 0]), 0.6667, places=4)

    def test_evi(self):
        # EVI(NIR 0.5, Red 0.1, Blue 0.05) = 2.5 x 0.4 / (0.5 + 0.6 - 0.375 + 1) = 1.0 / 1.725 = 0.57971
        value, ok = idx("EVI", nir=0.5, red=0.1, blue=0.05)
        self.assertTrue(ok)
        self.assertAlmostEqual(value, 0.5797, places=4)

    def test_ndmi(self):
        # (0.5 - 0.3) / (0.5 + 0.3) = 0.25
        self.assertAlmostEqual(idx("NDMI", nir=0.5, swir1=0.3)[0], 0.25, places=6)

    def test_nbr(self):
        # (0.5 - 0.1) / (0.5 + 0.1) = 0.6667
        self.assertAlmostEqual(idx("NBR", nir=0.5, swir2=0.1)[0], 0.6667, places=4)

    def test_ndvi(self):
        # (0.5 - 0.1) / (0.5 + 0.1) = 0.6667
        self.assertAlmostEqual(idx("NDVI", nir=0.5, red=0.1)[0], 0.6667, places=4)

    def test_ndwi_is_green_minus_nir(self):
        # water is brighter in green than in NIR: (0.4 - 0.1) / (0.4 + 0.1) = 0.6; vegetation reverses the sign
        self.assertAlmostEqual(idx("NDWI", green=0.4, nir=0.1)[0], 0.6, places=6)
        self.assertLess(idx("NDWI", green=0.1, nir=0.4)[0], 0)

    def test_mndwi(self):
        # (0.4 - 0.2) / (0.4 + 0.2) = 0.3333
        self.assertAlmostEqual(idx("MNDWI", green=0.4, swir1=0.2)[0], 0.3333, places=4)

    def test_ndre(self):
        # (0.6 - 0.3) / (0.6 + 0.3) = 0.3333
        self.assertAlmostEqual(idx("NDRE", nir=0.6, rededge=0.3)[0], 0.3333, places=4)

    def test_bsi(self):
        # ((0.3 + 0.2) - (0.4 + 0.1)) / ((0.3 + 0.2) + (0.4 + 0.1)) = 0 / 1.0 = 0; raise SWIR1 to 0.5: (0.7 - 0.5) / 1.2 = 0.16667
        self.assertAlmostEqual(idx("BSI", blue=0.1, red=0.2, nir=0.4, swir1=0.3)[0], 0.0, places=6)
        self.assertAlmostEqual(idx("BSI", blue=0.1, red=0.2, nir=0.4, swir1=0.5)[0], 0.1667, places=4)

    def test_every_index_stays_in_minus_one_to_one_for_reflectance_between_zero_and_one_except_evi_and_savi_edges(self):
        rng = np.random.RandomState(1)
        arrays = {role: rng.uniform(0.01, 0.9, (20, 20)) for role in ("blue", "green", "red", "rededge", "nir", "swir1", "swir2")}
        for index in ("NDVI", "NDWI", "MNDWI", "NDRE", "NDMI", "NBR", "BSI"):
            values, ok = ri.compute_index(index, arrays, np.ones((20, 20), dtype=bool))
            self.assertTrue(ok.all(), index)
            self.assertTrue(((values >= -1) & (values <= 1)).all(), index)


@unittest.skipUnless(HAVE_NUMPY, "numpy not installed")
class TestNoData(unittest.TestCase):
    def test_a_zero_denominator_is_no_data_not_zero(self):
        # NDVI with NIR = Red = 0: 0 / 0
        value, ok = idx("NDVI", nir=0.0, red=0.0)
        self.assertFalse(ok)
        self.assertEqual(value, 0.0)

    def test_savi_is_undefined_where_nir_plus_red_plus_l_is_zero(self):
        # NIR + Red + L = 0 needs L = -(NIR + Red); with L = 0.5 that is NIR + Red = -0.5
        _values, ok = ri.compute_index("SAVI", {"nir": one(-0.3), "red": one(-0.2)}, np.array([[True]]), soil_factor=0.5)
        self.assertFalse(bool(ok[0, 0]))

    def test_a_masked_input_cell_stays_undefined(self):
        self.assertFalse(idx("NDVI", valid=False, nir=0.5, red=0.1)[1])

    def test_nan_and_inf_inputs_are_undefined(self):
        _values, ok = ri.compute_index("NDVI", {"nir": np.array([[np.nan, np.inf, 0.5]]), "red": np.array([[0.1, 0.1, 0.1]])},
                                       np.ones((1, 3), dtype=bool))
        self.assertEqual(ok.tolist(), [[False, False, True]])

    def test_the_output_is_float32_with_the_input_shape(self):
        values, ok = ri.compute_index("NDVI", {"nir": np.full((3, 4), 0.5), "red": np.full((3, 4), 0.1)}, np.ones((3, 4), dtype=bool))
        self.assertEqual((values.dtype, values.shape, ok.shape), (np.float32, (3, 4), (3, 4)))


@unittest.skipUnless(HAVE_NUMPY, "numpy not installed")
class TestErrors(unittest.TestCase):
    def test_an_unknown_index_and_a_missing_band_are_errors_with_plain_messages(self):
        with self.assertRaises(ValueError) as ctx:
            ri.compute_index("XYZ", {}, np.array([[True]]))
        self.assertIn("NDVI", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            ri.compute_index("EVI", {"nir": one(0.5), "red": one(0.1)}, np.array([[True]]))
        self.assertIn("blue", str(ctx.exception))


class TestPureHelpers(unittest.TestCase):
    def test_names_roles_and_descriptions(self):
        self.assertEqual(ri.normalise_name(" savi "), "SAVI")
        self.assertIsNone(ri.normalise_name("ndvx"))
        self.assertEqual(ri.roles_for("evi"), ("nir", "red", "blue"))
        self.assertIsNone(ri.roles_for("nope"))
        self.assertIn("1 + L", ri.describe("SAVI")["formula"])
        self.assertIsNone(ri.describe(""))
        self.assertEqual(sorted(ri.INDICES), ["BSI", "EVI", "MNDWI", "NBR", "NDMI", "NDRE", "NDVI", "NDWI", "SAVI"])

    def test_the_scale_note_only_warns_for_the_scale_sensitive_indices(self):
        self.assertIn("digital numbers", ri.scale_note("EVI", 8500.0))
        self.assertIn("divide by 10000", ri.scale_note("savi", 3000.0))
        self.assertEqual(ri.scale_note("EVI", 0.9), "")
        self.assertEqual(ri.scale_note("NDVI", 8500.0), "")           # a normalised difference is the same at any scale
        self.assertEqual(ri.scale_note("XYZ", 8500.0), "")

    def test_band_references(self):
        self.assertEqual(ri.parse_band_ref("B8"), ("B8", 1))
        self.assertEqual(ri.parse_band_ref("scene@4"), ("scene", 4))
        self.assertEqual(ri.parse_band_ref("a@b@3"), ("a@b", 3))               # the last @ counts
        self.assertEqual(ri.parse_band_ref("name@x"), ("name@x", 1))           # not a band number: the whole text is a layer name
        self.assertEqual(ri.parse_band_ref("scene@0"), (None, None))
        self.assertEqual(ri.parse_band_ref("@2"), (None, None))
        self.assertEqual(ri.parse_band_ref(""), (None, None))

    def test_check_bands_names_what_is_wrong(self):
        self.assertIsNone(ri.check_bands("SAVI", {"nir": "B8", "red": "B4"}))
        self.assertIn("Missing: red", ri.check_bands("SAVI", {"nir": "B8"}))
        self.assertIn("does not use", ri.check_bands("NDVI", {"nir": "B8", "red": "B4", "blue": "B2"}))
        self.assertIn("not a supported index", ri.check_bands("XYZ", {"nir": "B8"}))
        self.assertIn("bands argument", ri.check_bands("NDVI", None))
        self.assertIn("Missing: red", ri.check_bands("NDVI", {"nir": "B8", "red": "  "}))


if __name__ == "__main__":
    unittest.main()
