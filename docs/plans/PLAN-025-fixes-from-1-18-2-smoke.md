# PLAN-025: fixes from the 1.18.2 hand smoke test

Status: in progress

## Goal
The owner ran the 1.18.2 build on 2026-10-26 (QGIS 4.2.3, Gemini provider) and returned results and 103 screenshots. Every defect in that run that can be traced to plugin code is fixed with a regression test; what cannot be traced without the CartogenAI log is named, not guessed at.

## Scope
In (numbers are the issue list sent to the owner):
1. A13: `search_stac_satellite_imagery` had no cloud-cover parameter, so "under 20 percent" returned unfiltered scenes and the model padded the table from memory. Now `max_cloud_cover` is sent to the service, results are newest first, the filters are echoed, an empty result says so.
2. C9: `score_route_incident_risk` applied the buffer distance in degrees on an EPSG:4326 route. Now buffered in real metres through the local UTM zone.
3. Confirmation cards: the four write previews (`calculate_severity_index`, `calculate_presence_gap`, `calculate_population_in_need`, `calculate_damage_exposure_severity`) showed a comment as "code"; they now show the write they make. The confirmation on those tools is the data-write gate, not the plan gate, so it is expected with `plan_validation_gate=OFF`.
4. Side effects: `generate_mapping_task_grid` gets `aoi_where` so one area can be gridded without filtering the source layer (the filter the owner saw on the admin layer).
5. Display: a `<br>` the model writes stays a line break; class text such as `$< 0.2$` loses its dollar signs; prices are untouched.
6. D5: loading the same file twice no longer adds a second layer and says it is already loaded, which stops the repeat that tripped the loop guard.
Out, with reasons: the A3 and A10 confirm clicks (no code path found that explains them; needs the log of those prompts), the unrequested "Incident" and country layers (no tool in the code adds them; they come from the model's plan, needs the log), the edit-mode pencil after B3 (`edit_command` commits and leaves the layer not editable when it started the session; covered by `tests/test_edit_session_live.py`; not reproduced), C5 inverted labels (no description of which labels), B1 nationwide 5 km grid refusal (a design decision for the owner), Overpass 502 (server side).

## Acceptance
1. Offline suite, ruff, `tools/ledger_guard.py` pass.
2. CI live passes, including the new live tests.
3. Hand (owner): re-run A13 with "under 20 percent cloud", C9 with the Aden convoy fixture, D5, and the B6 and A4 displays.

## Guard tests
tests/test_multimodal_remote_sensing.py::TestStacCloudFilter::test_cloud_limit_is_sent_to_the_service_and_echoed
tests/test_route_risk_metres_live.py::TestRouteRiskUsesMetres::test_500_m_catches_only_the_100_m_incident
tests/test_chat_formatting.py::TestModelBreaksAndComparisonSpans::test_model_written_br_stays_a_break_but_other_tags_stay_escaped
tests/test_task_grid_tools_live.py::TestGenerateMappingTaskGrid::test_aoi_where_limits_the_area_without_filtering_the_source_layer
tests/test_load_tabular_twice_live.py::TestLoadTabularTwice::test_second_identical_load_adds_nothing_and_says_so

## Rollback
Each fix is its own commit; revert the commit. Released fixes ship as 1.18.3.

## Status log
- 2026-10-26: plan written from the owner's results file and screenshots. Fixes 1 to 6 written with offline tests; live tests written without a local QGIS, so CI's first run is their first execution. Not hand-verified.
