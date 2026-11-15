"""Compatibility alias: `model_selector` moved to `cartogen_ai.core.model_selector` (PLAN-040 stage 3).

It has no dependency on the agent, and lower layers (providers, `core/net.py`, `core/models`) need it, so it now lives below the agent. This
file makes the old import path resolve to the SAME module object, so module state (for example `cancel_signal._state`) is shared and
`patch("cartogen_ai.core.agent.model_selector.<name>")` still patches the real module. New code imports the new path."""
import sys

from .. import model_selector as _moved

sys.modules[__name__] = _moved
