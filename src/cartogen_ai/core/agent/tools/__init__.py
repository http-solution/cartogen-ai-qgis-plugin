"""
Tools package for Cartogen AI.
Imports all tool modules to trigger tool registration into the central registry.
"""

from .registry import TOOL_REGISTRY, TOOLS_SCHEMA, get_tool_registry, get_tools_schema, register_tool

# Import tool modules to populate TOOL_REGISTRY & TOOLS_SCHEMA
from . import vector_tools
from . import data_source_tools
from . import attribute_edit_tools
from . import web_research_tools
from . import watershed_tools
from . import raster_calculator_tool
from . import symbology_tools
from . import map_view_tools
from . import raster_tools
from . import styling_tools
from . import export_tools
from . import system_tools
from . import task_tools
from . import tool_discovery
from . import corridor_tools
from . import dem_tools
from . import humanitarian_tools
from . import layout_tools
from . import db_and_workflow_tools
from . import multimodal_remote_sensing
from . import analysis_tools
from . import project_tools
from . import reporting_tools
from . import logistics_tools
from . import monitoring_tools
from . import imagery_extraction
from . import dataset_status_tools
from . import schema_contract_tools
from . import pcode_validation_tools
from . import provenance_tools
from . import qa_checklist_tools
from . import sensitivity_tools
from . import tool_operations_tools
from . import transaction_tools
from . import confidence_tools
from . import data_export_tools
from . import processing_allowlist_tools
from . import impedance_tools
from . import cartographic_advisory_tools
from . import hazard_monitoring_tools
from . import event_data_tools
from . import incident_search_tools
from . import fact_check_tools
from . import representation_tools
from . import map_tools
from . import project_tidy_tools
from . import engineering_tools
from . import barrier_tools
from . import trigger_tools
from . import task_grid_tools
from . import sampling_tools
from . import mcda_tools
from . import survey_tools
from . import humanitarian_look_tools
from . import allocation_tools
from . import table_importers
from . import critical_link_tools
from . import jiaf_inputs
from . import jiaf_engine
from . import jiaf_review
from . import jiaf_patterns

__all__ = [
    "TOOLS_SCHEMA",
    "TOOL_REGISTRY",
    "allocation_tools",
    "analysis_tools",
    "attribute_edit_tools",
    "barrier_tools",
    "cartographic_advisory_tools",
    "confidence_tools",
    "corridor_tools",
    "critical_link_tools",
    "data_export_tools",
    "data_source_tools",
    "dataset_status_tools",
    "db_and_workflow_tools",
    "dem_tools",
    "engineering_tools",
    "event_data_tools",
    "export_tools",
    "fact_check_tools",
    "get_tool_registry",
    "get_tools_schema",
    "hazard_monitoring_tools",
    "humanitarian_look_tools",
    "humanitarian_tools",
    "imagery_extraction",
    "impedance_tools",
    "incident_search_tools",
    "jiaf_engine",
    "jiaf_inputs",
    "jiaf_patterns",
    "jiaf_review",
    "layout_tools",
    "logistics_tools",
    "map_tools",
    "map_view_tools",
    "mcda_tools",
    "monitoring_tools",
    "multimodal_remote_sensing",
    "pcode_validation_tools",
    "processing_allowlist_tools",
    "project_tidy_tools",
    "project_tools",
    "provenance_tools",
    "qa_checklist_tools",
    "raster_calculator_tool",
    "raster_tools",
    "register_tool",
    "reporting_tools",
    "representation_tools",
    "sampling_tools",
    "schema_contract_tools",
    "sensitivity_tools",
    "styling_tools",
    "survey_tools",
    "symbology_tools",
    "system_tools",
    "table_importers",
    "task_grid_tools",
    "task_tools",
    "tool_discovery",
    "tool_operations_tools",
    "transaction_tools",
    "trigger_tools",
    "vector_tools",
    "watershed_tools",
    "web_research_tools",
]
