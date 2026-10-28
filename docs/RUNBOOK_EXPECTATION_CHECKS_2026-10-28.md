# Runbook expectation checks (DEF-16), 2026-10-28

DEF-16 was "runbook expectations to correct": rows where the 1.18.4 hand run failed because the **runbook** said the wrong thing, not the tool. The runbook is built outside the repo (the live-test package), so this page keeps the checked facts here, where the next package build can read them. Each line says what the row should expect, how that was checked, and what is still unproven.

## Checked against the fixtures (computed independently of the plugin)

| Row | Correct expectation | How checked |
|---|---|---|
| D7, N1, S1 | `damage_score` is min-max normalised 0 to 1: Khormaksar (YE2003) 1.0, Tur al Bahah (YE2005) about 0.64, the other four districts 0. The mean absolute change behind it is 70 and 45, but the field does **not** hold 70 and 45. | Read `before_fixture.asc` and `after_fixture.asc`, took the mean absolute difference of the cells whose centre falls in each district: 70.0, 45.0 and 0.0 for the four others (the signed means are -70 and -45). 45/70 = 0.643. The tool's method line is "min-max normalization to 0-1" (`_compute_severity_index`). |
| D7 | Building counts per district 2, 3, 4, 5, 6, 7 in the order Crater, Sira, Khormaksar, Dar Saad, Tur al Bahah, Habil Jabr (27 in all). | Counted `buildings_fixture.geojson` centroids inside each district polygon. |
| R3 | The two incidents near the point are dated 2026-10-05 and 2026-10-20 (the third, 2026-10-22, is far). A 30-day window: both count up to 2026-11-04; only 2026-10-20 counts from 2026-11-05 to 2026-11-19; **neither counts from 2026-11-20**. Before 2026-11-05 the date bound cannot be shown working: record SKIP for that part. | Read `incidents_fixture.geojson`. The earlier text stopped at 2026-11-05 and was wrong from 2026-11-20. |

## Checked against the tool's own wording

| Row | Correct expectation | Source |
|---|---|---|
| S5 (no threshold) | The tool refuses with `threshold is required and must be a number: it comes from your trigger protocol, there is no default.` A model that asks for the threshold without calling the tool also passes. The old text expected the words "no default threshold", which the tool never prints. | `trigger_tools.py`, the rule validator |
| A11 | The FTS tool's source line is `OCHA Financial Tracking Service (fts.unocha.org), live snapshot`; the reply must name OCHA FTS. | `humanitarian_tools.py`, `fetch_fts_funding_data` |
| C8 | The tool's note: `Shows how many shortest routes depend on each segment; it is not a closure simulation or a traffic forecast. One shortest path per pair; no congestion, convoy size or security.` The reply may paraphrase but must say it is not a closure simulation. | `critical_link_tools.py`, `screening_note` |
| N5 | The default output layer is `<layer>_obfuscated`, here `points_aden_fixture_obfuscated`; 0.01 degrees is about 1.1 km. | `vector_tools.py`, `obfuscate_sensitive_points` |

## Not changed, and why

- N1 already expected only the ranking and the absence of working columns; it was correct.
- N4 and N6 (blur and heatmap radius in metres on a lat/lon layer) were corrected earlier (DEF-15).
- C6: the demand points sit about 5 km from the nearest road, beyond the default 2,000 m snap, so a model that retries with a larger `max_snap_m` is behaving sensibly. A fixture note, not a tool fault.

## Not verified

These expectations were checked against files and code, not by running the plugin in QGIS. Whether a model produces the sentences is exactly what the hand run measures.
