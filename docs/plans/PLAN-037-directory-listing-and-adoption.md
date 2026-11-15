# PLAN-037: a directory listing people choose, and the proof next to it

Status: planned

## Goal
When a user compares AI plugins in the QGIS directory, this one is the obvious pick for humanitarian and field work. The repository has fewer than ten stars, and master list OWN-12 (publish on plugins.qgis.org, which needs the owner's login) is open, so visibility is a bigger limit than any missing feature.

## Scope
In:
1. **Listing pack** (prepared by Claude, uploaded by the owner): `metadata.txt` fields and tags checked against the directory rules in CONTRIBUTING section 9, a plain-language description, a changelog shown in the directory, an icon, screenshots of real results from the smoke fixtures (the evidence folders already hold them), and the licence note.
2. **A two-minute demo**: the verified result gate catching a wrong answer, an access analysis, a sitrep with its figures read from the layer. Shot on the smoke fixtures so anyone can repeat it.
3. **Worked examples**: one short page per tool family (damage, access, survey, JIAF support, forecast triggers), each with the fixture file, the exact prompt and the expected answer, taken from the runbook.
4. **A comparison page that is fair**: what this plugin does that the others in the analysis document do not (evidence trail, write gates, humanitarian tools) and what they do that it does not (3.x support, MCP, a managed cloud), updated as PLAN-031 to PLAN-036 land.
5. **A monthly record** in the master list: downloads, rating, votes, issues opened.
6. **Pilots**: two humanitarian teams asked to try the plugin on their own non-sensitive data, with the evidence folder as the feedback channel. The owner chooses the teams.
Out: paid promotion; claims about other plugins that this repository cannot support; any statement that the plugin is hand-verified where it is CI-verified only (the "what is verified" line stays on the page).

## Acceptance
1. The listing pack passes the directory's own upload checks (CONTRIBUTING section 9) before the owner uploads it.
2. Demo and examples: a person who has never used the plugin repeats one example from the page in under ten minutes (hand test with someone outside the project).
3. The comparison page's statements about the plugin are each checkable against `docs/FEATURE_LEDGER.json`.

## Guard tests
none, because this is content; the listing pack's metadata is covered by the existing release-docs and packaging tests.

## Rollback
Unpublish or edit the page; the plugin is unchanged.

## Status log
- 2026-10-28: plan written. Depends on LEAD-1 (positioning) and OWN-12 (publication).
