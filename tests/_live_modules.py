# -*- coding: utf-8 -*-
"""Which tests/test_*_live.py modules the qgis-live-tests CI job runs.

The runner used to list every live module by hand, and a module that was never added to the list simply never ran: the live
get_layers check in tests/test_agent_live.py was one of them, which is how the rc12 dict-only regression reached a release
(rc15 hand test, 2026-10-06). Now a module is picked up by name unless it is in EXCLUDED with a stated reason, and
tests/test_live_registration.py (offline) fails if an exclusion is stale or unexplained.

ORDER keeps the modules that already ran in the order they ran in, because the job's shutdown crash workaround (see
_ci_run_live_tests.py) is sensitive to what Qt objects exist; anything new runs after them, sorted by name. Pure: no QGIS."""
import os

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

ORDER = [
    "test_chat_widget_live", "test_plugin_main_live", "test_network_units_live", "test_network_background_live",
    "test_network_clip_live", "test_rc8_live", "test_facility_access_live", "test_worldpop_clip_live",
    "test_chat_transcript_live", "test_rc9_live", "test_routing_style_live", "test_output_style_live",
    "test_project_tidy_live", "test_processing_provider_live", "test_edit_session_live", "test_barrier_tools_live",
    "test_network_closure_live", "test_partial_edge_costs_live", "test_layout_swap_live", "test_humanitarian_look_live",
    "test_allocation_tools_live", "test_table_importers_live", "test_critical_link_tools_live", "test_jiaf_inputs_live",
    "test_jiaf_engine_live", "test_jiaf_review_live", "test_trigger_tools_live", "test_task_grid_tools_live",
    "test_sampling_tools_live", "test_mcda_tools_live", "test_survey_tools_live", "test_humanitarian_style_live",
    "test_processing_registry_diagnostic_live", "test_raster_numpy_live", "test_processing_allowlist_tools_live",
    "test_script_isolation_reconcile_live",
]

# module name -> why the CI job does not run it. Remove an entry to start running the module.
EXCLUDED = {
    "test_agent_live": ("never registered in the CI runner, so it has not been run there; enable it with a CI run to watch "
                        "(it drives the full agent pipeline with a scripted client)"),
}


def discovered():
    """Every live module on disk, by name."""
    return sorted(f[:-3] for f in os.listdir(TESTS_DIR) if f.startswith("test_") and f.endswith("_live.py"))


def live_module_names():
    """The modules to run, in order: ORDER first (those still on disk and not excluded), then the rest sorted."""
    on_disk = set(discovered())
    names = [n for n in ORDER if n in on_disk and n not in EXCLUDED]
    names += [n for n in sorted(on_disk) if n not in names and n not in EXCLUDED]
    return names
