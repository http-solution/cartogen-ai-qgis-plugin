"""context.json in an evidence folder: the settings and layer state a request ran in (rc48: two findings could not be reproduced without it)."""
import json
import os
import tempfile
import unittest

from cartogen_ai.core.agent.evidence import EvidenceRecorder


class TestEvidenceContext(unittest.TestCase):
    def test_finish_writes_context_json_when_a_context_was_set(self):
        folder = os.path.join(tempfile.mkdtemp(), "t1")
        recorder = EvidenceRecorder(folder, "merge the layers")
        recorder.context = {"egress": {"mode": "enforce", "strict": False}, "layers": [{"name": "smoke_points", "sensitivity": "SENSITIVE"}]}
        recorder.finish("done")
        with open(os.path.join(folder, "context.json"), encoding="utf-8") as fh:
            written = json.load(fh)
        self.assertEqual(written["egress"]["mode"], "enforce")
        self.assertEqual(written["layers"][0]["sensitivity"], "SENSITIVE")

    def test_no_context_writes_no_file(self):
        folder = os.path.join(tempfile.mkdtemp(), "t2")
        EvidenceRecorder(folder, "x").finish("done")
        self.assertFalse(os.path.exists(os.path.join(folder, "context.json")))

    def test_project_context_is_empty_outside_qgis(self):
        from cartogen_ai.core.agent import evidence
        try:
            import qgis.core  # noqa: F401
        except ImportError:
            self.assertEqual(evidence.project_context(), {})


if __name__ == "__main__":
    unittest.main()
