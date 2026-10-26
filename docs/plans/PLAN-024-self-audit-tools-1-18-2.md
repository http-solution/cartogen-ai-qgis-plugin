# PLAN-024: self-audit of every tool and release 1.18.2

Status: in progress

## Goal
A user who gives a tool a layer that is missing, of the wrong type or empty, or whose data service is down, slow or answers with an error page or a JSON body of the wrong shape, gets a clear message and never "Execution failed". Found by running every tool, not by reading them. The fixes ship as 1.18.2 together with the redirect-hop retry (PR 444). Requested by the owner on 2026-10-26 ("self audit for the other tools, make fixes whenever needed, the release 1.18.2").

## Scope
In: `tests/test_every_tool_live.py` second and third pass (hostile layer arguments: missing, wrong type, empty; hostile network answers: host unreachable, HTML error page, `[]`, `{}`, `null`), a static search for Qt6 enum misuse, a fix for every tool that raises, regression guards, version 1.18.2 release preparation (not publication).
Out: correctness of results (dedicated tests and hand rows do that); tools that read through GDAL /vsicurl or call the hosted model (named in `NO_STUB_SKIPS`); new features; the PLAN-023 programme.

## Acceptance
1. Offline: the suite, ruff, `tools/ledger_guard.py` pass.
2. CI live: `tests/test_every_tool_live.py` all passes with `KNOWN_HOSTILE_CRASHES` empty, or each remaining entry has a stated reason in this log.
3. Release prep: `tests/test_release_docs_in_sync.py` passes with version 1.18.2.
4. Hand (owner): the "create ADM1 Yemen" request on the machine where it failed.

## Guard tests
tests/test_every_tool_live.py::TestEveryToolLive::test_no_tool_raises_or_returns_nothing_on_plausible_arguments
tests/test_every_tool_live.py::TestEveryToolHostileInputsLive::test_layer_that_does_not_exist
tests/test_every_tool_live.py::TestEveryToolHostileInputsLive::test_json_that_is_a_list

## Rollback
Each fix is a separate commit in one pull request; revert the commit. A release is not rolled back: the previous release stays installable and a defect gets 1.18.3.

## Status log
- 2026-10-26: plan written. Static search for unscoped Qt enums and integer arguments to Qt setters: none left after the PR 444 fix (CI-checked by the first run of the every-tool test, which found two crashes, both fixed in PR 444). Hostile-input passes written; first CI run is their first execution.
