"""CI runners must not float: 'ubuntu-latest' is announced to move to Ubuntu 26.04, which would change the system Python, GDAL and Qt under every
job without a commit (CI annotation seen 2026-10-24). Move the pinned version on purpose, in its own pull request."""
import glob
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestRunnersPinned(unittest.TestCase):
    def test_no_workflow_uses_ubuntu_latest(self):
        found = []
        for path in sorted(glob.glob(os.path.join(ROOT, ".github", "workflows", "*.yml"))):
            with open(path, encoding="utf-8") as fh:
                for number, line in enumerate(fh, 1):
                    if "ubuntu-latest" in line and not line.lstrip().startswith("#"):
                        found.append(f"{os.path.basename(path)}:{number}")
        self.assertEqual(found, [], "pin the Ubuntu version (for example ubuntu-24.04)")

    def test_checkout_runs_on_node_24(self):
        """actions/checkout@v4 runs on Node 20, which GitHub is retiring (CI annotation, 2026-10-24: 'forced to run on Node.js 24'); v5 is Node 24."""
        found = []
        for path in sorted(glob.glob(os.path.join(ROOT, ".github", "workflows", "*.yml"))):
            with open(path, encoding="utf-8") as fh:
                for number, line in enumerate(fh, 1):
                    if "actions/checkout@v4" in line or "actions/checkout@v3" in line:
                        found.append(f"{os.path.basename(path)}:{number}")
        self.assertEqual(found, [], "use actions/checkout@v5 or later")


if __name__ == "__main__":
    unittest.main()
