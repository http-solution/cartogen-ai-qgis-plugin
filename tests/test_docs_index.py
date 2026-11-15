"""docs/SNAPSHOTS.md must list every dated or per-release doc (PLAN-040 stage 6)."""
import importlib.util
import os
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    spec = importlib.util.spec_from_file_location("docs_index", os.path.join(_ROOT, "tools", "docs_index.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class DocsIndexTests(unittest.TestCase):
    def test_snapshot_index_is_current(self):
        self.assertEqual(_load().main(["--check"]), 0, "run: python tools/docs_index.py")

    def test_living_docs_are_not_listed_as_snapshots(self):
        names = _load().snapshot_names()
        for living in ("IMPLEMENTATION_TRACKER.md", "BUG_TRACKER.md", "USER_GUIDE.md", "TOOLS_REFERENCE.md", "MASTER_TASK_LIST_2026-10-27.md"):
            self.assertNotIn(living, names)
        self.assertGreater(len(names), 50)


if __name__ == "__main__":
    unittest.main()
