## What this changes and why

<!-- Not just what the code does -- why. See CONTRIBUTING.md #1. -->

## How you verified it

<!-- A test run, a live QGIS session, a specific reproduction you checked by hand.
     "Should work" is not verification -- see CONTRIBUTING.md #4 and
     docs/RELEASE_SMOKE_TEST.md if this touches anything that needs a live QGIS check. -->

## Status

- [ ] Shipped and verified (tests pass / manually confirmed live)
- [ ] Shipped but unverified against a live QGIS session (say so in the code, per CONTRIBUTING.md #2)
- [ ] Roadmap / partial — describe what's left and where that's tracked (issue link or
      `docs/IMPLEMENTATION_TRACKER.md`)

## Checklist

- [ ] `python -m unittest discover -s tests -p "test_*.py"` passes locally
- [ ] New/changed behavior has test coverage, or an explanation of why it can't be tested here
- [ ] Docs updated in the same change if this makes a previously-documented "not yet built" or
      "roadmap" item shipped (CONTRIBUTING.md #2) — don't let the docs go stale
- [ ] If this is a judgment call rather than a mechanical fix, it's flagged for review rather than
      applied silently (CONTRIBUTING.md #3)
