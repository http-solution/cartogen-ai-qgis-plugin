# LR-27: cut release 1.20.0, or hold? A decision aid, 2026-11-23

Written for the owner. Nothing here has been applied: no version bump, no tag, no release. Facts come from the repository (counted with `git` on 2026-11-23); judgement is marked as mine.

## The question
Master-list row LR-27: the fixes of 2026-11-20 and everything after them are on `main` but unreleased. Cut 1.20.0 (version bump, Help, README, CHANGELOG, counts), or decide to hold.

## Facts
- **Last release:** 1.18.5 (tag `cartogen-ai-v1.18.5`, 2026-10-28). `metadata.txt` on `main` still says `version=1.18.5`.
- **Since then:** 766 commits on `main`, about 360 merged pull requests (counted from commit titles), 247 source files changed (+24,938 / -4,602 lines).
- **Tools:** 294 in 1.18.5, 336 now (+42). Offline test files: 411 then, 645 now.
- **Built since 1.18.5 (all merged, CI green):** the persona packs (R1), spatial statistics (R2), the layout looks, geometry editing (R9), attribute and raster rows (R10), Processing models and waves (R11), the routing fix for plain requests (issue 380: confident task matches over the 385 plain prompts 34 to 7), the map button in the chat (RM-B), and the fail-closed protection work of 2026-11-22 (an unreadable protection tag, layer list, selection or QGIS setting now blocks or protects instead of passing).
- **What a user would notice on update:** new tools in the picker; a layer with a damaged protection tag now shows as SENSITIVE and asks before an export or cloud send; when QGIS settings cannot be read the egress gate enforces; an export refuses when it cannot tell whether features are selected (unless `only_selected=false`); a map button next to the paperclip.

## What is NOT known
- Almost all of this passed CI (offline suite, ruff, the live QGIS 4.2.2 job) but **has not been run by a person on real data**. Four open issues cover what a person has to run: 380 (routing; rows B28, B32 and B41 to re-run), 510 (Connections window, Claude Code and Codex setup), 576 (legend, dashboard, result checks), 635 (spatial statistics against published tools). No checklist item in 510, 576 or 635 is ticked.
- Real-data rows for R2 wait on a case-count file (OWN-14).
- The fail-closed behaviours were tested with fakes; none was seen on a real QGIS failure.
- The map button has never been seen on screen, and no real model has been asked to use it.
- Row LR-13 (why the evidence dock recorded nothing on the owner's machine) is still open and is a dependency of this row.

## What a release needs (CONTRIBUTING section 8)
Version in `metadata.txt` plus a new `changelog=` block, a CHANGELOG row and section, `release_notes.py` (What's new, new-tool marks), the README (version line, status line, What's new, humanitarian table), and the counts. `tests/test_release_docs_in_sync.py` fails until they agree. No code change; my estimate is about half a day of careful editing.

## Options
- **(a) Cut a stable 1.20.0 now.** Users get the 42 new tools and the protection changes. Risk: a large amount of CI-only code reaches everyone at once, and the first real-data feedback arrives after release.
- **(b) Hold.** Nothing reaches users; the gap to 1.18.5 keeps growing (766 commits today) and each later release has more to verify at once.
- **(c) Cut it as a pre-release (for example 1.20.0-rc1) and promote it to stable only when named hand rows pass.** The project has done this before (1.16.0-rc7 to rc10 were published as pre-releases). Users on the stable channel are not affected; testers get a package built from `main`.

## Recommendation (mine, not measured): (c)
It is the only option that gets real-data evidence without putting unverified code in front of everyone. Suggested exit criteria for promoting to stable: rows C21 to C27 of issue 635 that do not need the case-count file, the routing rows of issue 380, and the Connections rows of issue 510. If you prefer (a), the protection changes are the part I would watch first; if (b), the cost is the growing gap.

## What I need from you
Pick (a), (b) or (c). I will not bump the version, tag or release without your explicit go.
