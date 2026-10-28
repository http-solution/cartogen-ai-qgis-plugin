# PLAN-036: should the plugin support QGIS 3.x? (a study, then a decision)

Status: planned

## Goal
Replace a guess with a number before the owner decides. The plugin requires QGIS 4.2 and later (Qt6): support for 3.x was dropped on 2026-09-24 and `qgisMinimumVersion` is 4.2. The competitors in the analysis document list 3.22 or 3.28 upward, and the long-term-release 3.x installations are probably where most users still are (an assumption: this repository has no download or version statistics), so the choice may limit the audience of the directory listing. The cost of supporting 3.x is not known; this plan finds it out. No code is changed.

## Scope
In (a study written into this plan):
1. Inventory what differs: Qt5 against Qt6 enum and import use across `src/` (the documents name `getattr` fallbacks as the common pattern), PyQGIS API differences for the calls this plugin makes (Processing, layouts, network access, labelling, the layer tree), Python version floor (3.9 on 3.28), and optional dependencies.
2. Count: files and call sites affected, grouped by kind, from a script that is kept in `tools/` so the number can be rerun.
3. CI cost: the QGIS 3.28 and 3.40 images, the live-test runtime, and which of the 5,100 tests assume Qt6.
4. A recommendation with a size estimate, three options (stay 4.2+; support the current 3.x LTR only; support 3.28 upward) and what each loses.
Out: any change to the plugin; the 4.2-only code path must keep working.

## Acceptance
1. The inventory script runs and its counts are in the status log.
2. The three options each have a cost in working days and a risk list.
3. The owner's decision (LEAD-2) is recorded here, in the master list and in `docs/IMPLEMENTATION_TRACKER.md` section 1.
Nothing here can be hand-verified; the study's numbers are checkable by rerunning the script.

## Guard tests
none, because the study changes no behaviour; the inventory script gets a unit test if it is kept.

## Rollback
Nothing to roll back.

## Status log
- 2026-10-28: plan written. The study can start without the decision.
