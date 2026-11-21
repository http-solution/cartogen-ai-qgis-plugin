"""Import this FIRST in a test module that needs the `requests` library: without it the module is skipped (not errored).

Why (LR-25): every offline run in a sandbox that lacks `requests` printed 51 errors (49 in test_providers, one in test_stop_during_model_call, one for
test_account_client failing to import) and a person had to know they were the expected baseline. A skip says so, and a real error is no longer buried in them.

`requests` is a declared dependency (requirements.txt), and CI installs it. So that the skip can never hide a broken CI install,
tests/test_requests_present_in_ci.py fails when CI is set and `requests` cannot be imported."""
import unittest

try:
    import requests  # noqa: F401
except ImportError as exc:
    raise unittest.SkipTest("the `requests` library is not installed here (CI installs it and fails if it is missing)") from exc
