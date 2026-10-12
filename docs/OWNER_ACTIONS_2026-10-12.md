# What is left, and only you can do it (2026-10-12, build rc37)

A dated checklist, not a result. Everything that can be done from the repository was done; each item below needs your account, your data or a desktop QGIS
session. Nothing here has been done.

## 1. Hand test of rc37 in desktop QGIS (closes most of the 46 open issues)
1. Install `cartogen_ai_v1.16.0-rc37.zip` (check it against `SHA256.txt`: `28f6fdba665f1a75ef4cf993c86424fc07b5d266dfe209bf6faf28def17a40fe`) in a fresh QGIS 4.2 profile.
2. `python tools/live_test_pack.py prepare C:/Cartogen-AI-Smoke/rc37`, then work through `docs/FULL_LIVE_TEST_rc34.md` and fill `results/results.csv`.
3. `python tools/live_test_pack.py check C:/Cartogen-AI-Smoke/rc37 --strict`.
4. New in rc36 / rc37, not in the pack's rows yet, worth a look while you are there:
   - Freezes: on a project with a few large layers, run a hub-siting or service-area request. The window should keep repainting, and Stop should end the
     tool within about a second.
   - A long chat session (over 300 messages): the oldest should drop off the window, the plan card and tool-step toggles should still respond.
   - "Check the internet for incidents in <country> in the last 30 days": the reply should name the sources it checked and the ones it did not search,
     and a map layer named "Incident reports" should appear. If the assistant uses the web search instead, send me the exact prompt.
5. Close each GitHub issue whose rows pass, with the evidence in a comment. The status of the 46 open issues is in `docs/OPEN_ISSUES_STATUS_2026-10-11.md`.

## 2. plugins.qgis.org upload
Needs your plugins.qgis.org login. Upload the rc37 zip, then read the scan report and tell me what it says. Locally the same checks pass
(`tests/test_directory_validator.py`, `tests/test_metadata_parses.py`); the directory has refused a build before for a reason only its own parser sees
(a percent sign in an old changelog block, fixed in rc24).

## 3. JIAF validation blockers (task 69)
The tools carry two open blockers in every result on purpose. I cannot close either without your material:
- **Flag formulas:** a Flags dashboard export or the analysis team's records for one real country, showing the same flags my implementation gives, including
  missing, zero and partly filled inputs; a populated historical table for flag 6; the flag-3 case where the third-highest PiN is exactly 0 on real worksheet
  output; the thresholds sheet of a real country workbook.
- **Annex 4 reader:** one real, filled Annex 4 sector-input file.
Send those and I will run the comparison and report each difference; closing the blockers is still your decision.

## 4. Optional: more sources for `find_incident_reports`
- **ReliefWeb structured API:** it refuses an unregistered application name. Request one at https://apidoc.reliefweb.int/parameters#appname (a short form: your
  organisation, the plugin name "Cartogen AI", its public repository URL, and that it queries disasters and reports for humanitarian mapping, read-only, a few
  requests per user session). When you have the name, tell me; the tool currently uses the ReliefWeb RSS feed, which has no coordinates or filters.
- **ACLED:** needs a registered key and agreement to its terms; it would be stored in the QGIS Auth Manager like the AI provider keys (tracker HX4).
- **Fact-checkers:** Reuters, AFP and Full Fact offer no feed a program may read, so there is nothing to build until one of them provides access.
