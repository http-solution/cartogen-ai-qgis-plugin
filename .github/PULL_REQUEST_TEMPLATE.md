## What this changes and why

<!-- Not just what the code does -- why. See CONTRIBUTING.md #1. -->

## How you verified it

<!-- A test run, a live QGIS session, a specific reproduction you checked by hand.
     "Should work" is not verification -- see CONTRIBUTING.md #4 and
     docs/RELEASE_SMOKE_TEST.md if this touches anything that needs a live QGIS check. -->

## Before / after

<!-- Required when this touches routing, prompts, tools or settings. Show what a user could do before and what they can do now;
     "same" is a valid answer and is what proves nothing regressed. Add a row for every request you checked. -->

| Request a user would type | Before this PR | After this PR |
|---|---|---|
| | | |

- [ ] Tool count before / after: ___ / ___ (a drop needs a reason; `tests/test_tool_schema_snapshot.py` fails on a removal)
- [ ] Any golden table row added, never removed (`tests/test_golden_suite_size_pins.py`)

## Status

- [ ] Shipped and verified (tests pass / manually confirmed live)
- [ ] Shipped but unverified against a live QGIS session (say so in the code, per CONTRIBUTING.md #2)
- [ ] Roadmap / partial — describe what's left and where that's tracked (issue link or
      `docs/IMPLEMENTATION_TRACKER.md`)

## Plan, ledger and guards (CONTRIBUTING.md section 10)

- [ ] Plan: `docs/plans/PLAN-___` created or its status log updated (or "no behaviour change")
- [ ] Ledger: `docs/FEATURE_LEDGER.json` entry added or updated, with guard tests that fail without this change
- [ ] `python tools/ledger_guard.py` run: every ledger feature this change touches still passes
- [ ] Hand-verified claim is specific ("CI only" / "hand-tested on rcNN, row ID")

## Checklist

- [ ] `python -m unittest discover -s tests -t . -p "test_*.py"` passes locally
- [ ] New/changed behavior has test coverage, or an explanation of why it can't be tested here
- [ ] Docs updated in the same change if this makes a previously-documented "not yet built" or
      "roadmap" item shipped (CONTRIBUTING.md #2) — don't let the docs go stale
- [ ] If this is a judgment call rather than a mechanical fix, it's flagged for review rather than
      applied silently (CONTRIBUTING.md #3)
