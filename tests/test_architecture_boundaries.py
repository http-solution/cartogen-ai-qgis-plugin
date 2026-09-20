# -*- coding: utf-8 -*-
"""
Tests verifying clean architectural package boundaries:
- cartogen_ai.infrastructure
- cartogen_ai.processing
- cartogen_ai.core.models
- cartogen_ai.core.validators
- cartogen_ai.core.services
"""

import unittest


class TestArchitectureBoundaries(unittest.TestCase):
    def test_infrastructure_boundary(self):
        import cartogen_ai.infrastructure as infra

        self.assertTrue(hasattr(infra, "CredentialManager"))
        self.assertTrue(hasattr(infra, "get_qgis_proxy_dict"))
        self.assertTrue(callable(infra.get_qgis_proxy_dict))

    def test_auth_importable_without_infrastructure_already_loaded(self):
        # Originally added for a real bug found in a code-review pass (2026-09-20):
        # cartogen_ai.infrastructure's __init__.py used to eagerly
        # `from ..core.agent.auth import CredentialManager` while auth.py itself still lived
        # in core.agent and reached back into infrastructure.settings_keys -- a genuine
        # circular import, masked by test discovery order (see git history of this file for
        # the original writeup). Superseded 2026-09-20 by the real Phase 11 architecture
        # move (docs/IMPLEMENTATION_TRACKER.md §4): auth.py now physically lives in
        # cartogen_ai.infrastructure itself, so the cross-package cycle this test guarded
        # against can no longer exist by construction -- infrastructure/__init__.py now
        # imports CredentialManager from its own sibling module eagerly, no __getattr__
        # deferral needed. Kept as a plain regression check (import in a clean subprocess,
        # from the new real location) rather than deleted outright, so a future change that
        # reintroduces a real cycle here still gets caught.
        import subprocess
        import sys
        import os

        src_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
        result = subprocess.run(
            [sys.executable, "-c", "from cartogen_ai.infrastructure.auth import CredentialManager"],
            capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": src_dir},
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_processing_boundary(self):
        import cartogen_ai.processing as proc

        self.assertTrue(hasattr(proc, "CartogenProcessingProvider"))
        self.assertTrue(hasattr(proc, "OptimalHubSitingAlgorithm"))
        self.assertTrue(hasattr(proc, "CalculateServiceAreaAlgorithm"))

    def test_models_boundary(self):
        import cartogen_ai.core.models as models

        self.assertTrue(hasattr(models, "TurnTransactionLog"))
        self.assertTrue(hasattr(models, "STATUS_ORDER"))
        self.assertTrue(hasattr(models, "get_dataset_status"))
        self.assertTrue(hasattr(models, "advance_dataset_status"))
        self.assertTrue(hasattr(models, "set_initial_status"))
        self.assertTrue(hasattr(models, "SENSITIVITY_LEVELS"))
        self.assertTrue(hasattr(models, "CONFIDENCE_LEVELS"))

    def test_validators_boundary(self):
        import cartogen_ai.core.validators as validators

        self.assertTrue(hasattr(validators, "list_contracts"))
        self.assertTrue(hasattr(validators, "validate_layer_schema"))
        self.assertTrue(hasattr(validators, "check_pcode_uniqueness"))
        self.assertTrue(hasattr(validators, "check_pcode_hierarchy"))
        self.assertTrue(callable(validators.list_contracts))

    def test_services_boundary(self):
        import cartogen_ai.core.services as services

        self.assertTrue(hasattr(services, "refine"))
        self.assertTrue(hasattr(services, "should_refine"))
        self.assertTrue(hasattr(services, "ToolRouter"))
        self.assertTrue(hasattr(services, "AgentQgsTask"))
        self.assertTrue(hasattr(services, "maybe_infer_preferences"))


if __name__ == "__main__":
    unittest.main()
