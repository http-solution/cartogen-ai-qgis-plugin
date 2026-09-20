# -*- coding: utf-8 -*-
"""
cartogen_ai.core.services -- Core agent orchestration services.

Houses prompt refinement, tool routing, background task execution, and learning services.
"""

from .prompt_refiner import (
    refine,
    should_refine,
    build_refinement_messages,
    parse_refinement_response,
)
from .tool_router import ToolRouter
from .task_runner import AgentQgsTask
from .learning import (
    maybe_infer_preferences,
    detect_correction,
    record_correction_rule,
)

__all__ = [
    "refine",
    "should_refine",
    "build_refinement_messages",
    "parse_refinement_response",
    "ToolRouter",
    "AgentQgsTask",
    "maybe_infer_preferences",
    "detect_correction",
    "record_correction_rule",
]
