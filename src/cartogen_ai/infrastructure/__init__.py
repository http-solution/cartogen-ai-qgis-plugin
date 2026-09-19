# -*- coding: utf-8 -*-
"""
Infrastructure boundary package for Cartogen AI.
Houses external networking, authentication, settings, and environment abstractions.
"""

from ..core.proxy import get_qgis_proxy_dict
from . import settings_keys

__all__ = ["CredentialManager", "get_qgis_proxy_dict", "settings_keys"]


def __getattr__(name):
    # CredentialManager is deliberately NOT imported eagerly above -- core.agent.auth itself
    # imports from this package (`from ...infrastructure.settings_keys import ...`), so an
    # eager `from ..core.agent.auth import CredentialManager` here creates a real circular
    # import: importing cartogen_ai.core.agent.auth first runs this __init__.py (to reach
    # settings_keys), which then tried to import auth.py back from itself while it was still
    # mid-initialization -- "cannot import name 'CredentialManager' from partially
    # initialized module." Confirmed as a live crash (not theoretical) in a code-review pass
    # (2026-09-20): `python -m unittest tests.test_auth_and_deps` failed outright, even
    # though the full suite happened to pass because some other test file already finished
    # importing auth.py first and masked the ordering dependency. Deferred via PEP 562
    # module __getattr__ so the import only happens the first time something actually reads
    # `cartogen_ai.infrastructure.CredentialManager`, well after both modules have finished
    # initializing -- `infra.CredentialManager` (see test_architecture_boundaries.py) still
    # works identically, just resolved lazily instead of at package-import time.
    if name == "CredentialManager":
        from ..core.agent.auth import CredentialManager
        return CredentialManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
