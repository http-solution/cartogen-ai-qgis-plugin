import unittest

from cartogen_ai.core.agent.tools.project_ops_options import (check_annotation_text, check_metadata, check_snapping, check_time_range,
                                                              relation_id)


class ProjectOpsOptionsTests(unittest.TestCase):
    def test_metadata(self):
        out, err = check_metadata(title="Roads", keywords=["a", "b"], contact_name="N", contact_email="n@x.org")
        self.assertIsNone(err)
        self.assertEqual(out["keywords"], ["a", "b"])
        for kwargs in ({}, {"title": "x" * 301}, {"title": "a\x00b"}, {"keywords": "abc"}, {"contact_email": "nope"},
                       {"keywords": ["x"] * 51}):
            self.assertIsNotNone(check_metadata(**kwargs)[1], kwargs)

    def test_snapping(self):
        out, err = check_snapping(enabled=True, snap_type="Vertex and segment", tolerance="12", units="pixels", mode="all_layers")
        self.assertIsNone(err)
        self.assertEqual((out["type"], out["units"], out["mode"], out["tolerance"]), ("VertexAndSegment", "Pixels", "AllLayers", 12.0))
        for kwargs in ({}, {"snap_type": "teleport"}, {"tolerance": 0}, {"tolerance": "x"}, {"units": "miles"}, {"mode": "x"}):
            self.assertIsNotNone(check_snapping(**kwargs)[1], kwargs)

    def test_relation_id(self):
        self.assertEqual(relation_id(" districts schools ")[0], "districts schools")
        self.assertIsNotNone(relation_id("1bad")[1])
        self.assertIsNotNone(relation_id("a;b")[1])

    def test_time_range(self):
        self.assertIsNone(check_time_range("2026-03-01", "2026-03-31T12:00:00")[1])
        self.assertIsNotNone(check_time_range("2026-03-31", "2026-03-01")[1])
        self.assertIsNotNone(check_time_range("yesterday", "2026-03-01")[1])

    def test_annotation_text(self):
        self.assertEqual(check_annotation_text("  hi ")[0], "hi")
        self.assertIsNotNone(check_annotation_text("")[1])
        self.assertIsNotNone(check_annotation_text("x" * 501)[1])


if __name__ == "__main__":
    unittest.main()
