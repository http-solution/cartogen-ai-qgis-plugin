# -*- coding: utf-8 -*-
"""
Agent Task & Memory Tools for Cartogen AI.
Exposes tool functions allowing the LLM to manage task plans, preview safety checks, and memory.
"""

from typing import List, Optional
from .registry import register_tool

# References to active agent instance components will be bound dynamically or via runtime lookup
_TASK_MANAGER = None
_MEMORY_MANAGER = None


def bind_agent_context(task_manager, memory_manager):
    """Binds active TaskManager and MemoryManager instances to tool handlers."""
    global _TASK_MANAGER, _MEMORY_MANAGER
    _TASK_MANAGER = task_manager
    _MEMORY_MANAGER = memory_manager


@register_tool("create_plan", "Create a multi-step execution plan for complex spatial tasks.", {"type": "object", "properties": {"title": {"type": "string"}, "task_descriptions": {"type": "array", "items": {"type": "string"}}}, "required": ["title", "task_descriptions"]})
def create_plan(title: str, task_descriptions: List[str]):
    if _TASK_MANAGER is None:
        return {"error": "Task manager not initialized."}
    return _TASK_MANAGER.create_plan(title, task_descriptions)


@register_tool("set_task_preview", "Set a task to PREVIEW_READY state before applying destructive spatial edits.", {"type": "object", "properties": {"task_id": {"type": "string"}, "code_snippet": {"type": "string"}, "rationale": {"type": "string"}, "is_destructive": {"type": "boolean"}}, "required": ["task_id", "code_snippet"]})
def set_task_preview(task_id: str, code_snippet: str, rationale: str = "", is_destructive: bool = True):
    if _TASK_MANAGER is None:
        return {"error": "Task manager not initialized."}
    return _TASK_MANAGER.set_task_preview(task_id, code_snippet, rationale, is_destructive)


@register_tool("update_task", "Update status of a task in current plan (TODO, IN_PROGRESS, PREVIEW_READY, CONFIRMED, DONE, FAILED).", {"type": "object", "properties": {"task_id": {"type": "string"}, "status": {"type": "string"}, "result": {"type": "string"}, "rationale": {"type": "string"}, "code_snippet": {"type": "string"}}, "required": ["task_id", "status"]})
def update_task(task_id: str, status: str, result: str = "", rationale: str = "", code_snippet: str = ""):
    if _TASK_MANAGER is None:
        return {"error": "Task manager not initialized."}
    return _TASK_MANAGER.update_task(task_id, status, result, rationale, code_snippet)


@register_tool("store_project_memory", "Store persistent key-value note for current project.", {"type": "object", "properties": {"key": {"type": "string"}, "value": {"type": "string"}}, "required": ["key", "value"]})
def store_project_memory(key: str, value: str):
    if _MEMORY_MANAGER is None:
        return {"error": "Memory manager not initialized."}
    return _MEMORY_MANAGER.store_project_note(key, value)


@register_tool("store_global_memory", "Store persistent global preference/note across sessions.", {"type": "object", "properties": {"key": {"type": "string"}, "value": {"type": "string"}}, "required": ["key", "value"]})
def store_global_memory(key: str, value: str):
    if _MEMORY_MANAGER is None:
        return {"error": "Memory manager not initialized."}
    return _MEMORY_MANAGER.store_global_note(key, value)
