"""The skip in tests/_needs_requests.py is for a developer's sandbox only: in CI a missing `requests` is a broken install and must fail loudly (LR-25)."""
import importlib.util
import os
import unittest


class TestRequestsIsInstalledWhereItMatters(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("CI") == "true", "only checked where CI=true (GitHub Actions sets it)")
    def test_requests_can_be_imported_in_ci(self):
        self.assertIsNotNone(importlib.util.find_spec("requests"),
                             "`requests` is not installed in CI: 49 provider tests would be skipped instead of run. Fix the dependency install step.")

    def test_the_guard_module_skips_only_when_requests_is_missing(self):
        # Importing the guard must succeed where requests exists, and raise SkipTest where it does not; either way it never errors.
        try:
            import tests._needs_requests  # noqa: F401
        except unittest.SkipTest:
            self.assertIsNone(importlib.util.find_spec("requests"))
        else:
            self.assertIsNotNone(importlib.util.find_spec("requests"))


if __name__ == "__main__":
    unittest.main()
