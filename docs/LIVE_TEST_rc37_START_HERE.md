# Live smoke test: rc37 (start here)

This is the short guide. It adds **23 rows (`RC37-*`)** for what changed after rc34 (rc35 to rc37) to the existing full pack, and tells you which of the older rows to run. Nothing in rc23 to rc37 has been hand-tested; CI was green on each build, including live checks in QGIS 4.2.2, but no person has run these rows against a real model provider. Treat every row as unverified until you have the evidence.

## What you have (if you received the bundle zip)

| Path | What it is |
|---|---|
| `plugin/cartogen_ai_v1.16.0-rc37.zip` + `plugin/SHA256.txt` | The plugin to install |
| `docs/LIVE_TEST_rc37_START_HERE.md` | This guide |
| `docs/FULL_LIVE_TEST_rc37_ROWS.csv` | The 23 new rows |
| `docs/FULL_LIVE_TEST_rc34.md` + `docs/FULL_LIVE_TEST_rc34_ROWS.csv` | The full procedure and its 179 older rows (all rules, evidence rules and the fixture inventory live there) |
| `docs/release_smoke_assets/inputs/` + `docs/FULL_LIVE_TEST_rc34_INPUTS.sha256` | Synthetic Amman-area fixtures and their checksums |
| `tools/live_test_pack.py` | `prepare` builds the run folder; `check` reports missing evidence |
| older sheets, `RELEASE_LIVE_TEST_SCENARIOS.md`, `RC22_*` | Source of the exact wording of the older rows |

## 1. Prerequisites

- QGIS **4.2.x** and a **fresh profile** (Settings > User Profiles > New profile, then start QGIS with it). Delete any old `cartogen-ai` folder from `python/plugins` first.
- Python 3.10+ on your PATH (only for the helper; it runs outside QGIS and needs no packages).
- A model provider: Google Gemini (note whether the key's project is free or paid), OpenRouter, or local Ollama. Do not test the "Cartogen API" entry; no hosted gateway exists.
- Internet for the data rows (USGS, GDACS, EONET, UCDP, ReliefWeb, geocoding). Note any proxy or VPN.
- **Data rule:** every prompt goes to the model provider together with what the agent reads (layer and field names, counts, results). Use only the synthetic fixtures. Never paste an API key into a note, screenshot or report; write only its last four characters if a row asks.
- Keep QGIS's Network Logger panel closed while a key is configured.

## 2. Set up (about 10 minutes)

1. Verify the zip: compare its SHA-256 with `plugin/SHA256.txt` (Windows: `certutil -hashfile cartogen_ai_v1.16.0-rc37.zip SHA256`; macOS/Linux: `shasum -a 256 ...`).
2. Build the run folder (any empty writable folder; it is called TEST_ROOT):

   ```
   python tools/live_test_pack.py prepare C:/Cartogen-AI-Smoke/rc37
   ```

   It checks every fixture against its checksum, copies them to `TEST_ROOT/inputs/`, and writes `results/results.csv` (202 rows, the file you fill in) and `results/prompts_filled.csv` (every prompt with real paths; paste from this file, not from a document).
3. Install the zip (Plugins > Manage and Install Plugins > Install from ZIP), restart QGIS **twice**.
4. Open **View > Panels > Log Messages** and keep it visible.
5. Open `TEST_ROOT/inputs/smoke_start.qgz` (seven layers should load; if one does not, stop and repair the copy).
6. In Settings choose the provider, model **auto (recommended)**, and enter the key. Tick **"Record every model request and reply to a local folder (diagnostics)"** if you want an API trace; it stays on your disk.
7. Screenshot `screenshots/00_start.png`: the seven layers, the Log Messages panel and the Cartogen dock.

## 3. Order of work

Run in this order; each phase can be its own session.

1. **Phase 0, install gate (15 min):** `RC37-I1`, `RC37-I2`, `RC37-I3`. Nothing else is worth running until "Hello." gets a real reply. If it does not, the error line now says what each model answered and which key was sent (length and last four characters only).
2. **Phase 1, the rc35 to rc37 features:** `RC37-A1`, `A2` (research ends with an answer), `RC37-N1` to `N4` (incident search), `RC37-E1` to `E3` (earthquakes, conflict events), `RC37-W1`, `W2` (URL downloads).
3. **Phase 2, responsiveness (rc36):** `RC37-F1` to `F5`, `RC37-P1`. `F6` (160 messages) and `F7` (scheduler) are optional and long. For F2 and F5 the point is that **QGIS never shows "Not Responding" and Stop is heard**.
4. **Phase 3, regression:** `RC37-P2`, then the older pack in the order the full procedure gives (section 7 of `docs/FULL_LIVE_TEST_rc34.md`): the 16 categories `SC-A1` to `SC-C5`, then groups R, N, A, H, F, D, V, T, J, K, P. Open a **new chat** before every row that says NEW CHAT.
5. **Phase 4, upgrade gate:** `GATE-3` to `GATE-7`.

If you only have time for one session, do Phases 0 to 2 (about 21 new rows plus the install gate).

## 4. Per row

1. Copy the prompt from `results/prompts_filled.csv` and send it unchanged.
2. Read any confirmation card **before** approving (operation and target).
3. Check the Activity panel for the tool call that actually ran and the real layer, file or canvas. A plausible chat answer without an artifact is not a pass.
4. Count the `model_call` lines for the request (tag `Agent` in Log Messages). More than 4 calls for a simple request is a finding.
5. Save a screenshot named `screenshots/<row id>.png` (or `<row id>_<what>.png`).
6. Fill `result` (`PASS`, `PASS (degraded)`, `FAIL`, `INCONCLUSIVE`, `NOT RUN` with the reason, `SKIP`), `model_calls`, and `notes`. Never write a pass you inferred.
7. On a FAIL, paste the relevant Log Messages lines (no keys) into `notes` or `logs/`.

## 5. Things to watch for in this build

- **Research stalls:** a read-only request used to end as "[Agent stopped] ... NOT complete". It should now end with an answer. If you still see that text with search results gathered, that is a FAIL.
- **Incident search honesty:** an empty result must say which sources answered, which could not be reached and which were not searched. UCDP data are preliminary and weeks old; GDACS is global only (filtered locally); ReliefWeb items have no coordinates.
- **Freezes:** the 1.16 work slices about 90 loops into ~50 ms pieces. If QGIS still freezes, note which prompt, how long, and what the Log Messages panel shows.
- **Python Processing algorithms** (for example slope) deliberately stay on the main thread, so a short pause there is expected, not a defect. A crash is.

## 6. Check your evidence at any time

```
python tools/live_test_pack.py check C:/Cartogen-AI-Smoke/rc37
python tools/live_test_pack.py check C:/Cartogen-AI-Smoke/rc37 --strict
```

It reports result counts, rows with a result but no screenshot, promised output files that are missing, and rows over 4 model calls, and writes `results/summary.md`. `--strict` exits 1 if any row has a result without evidence. It never edits `results.csv`.

## 7. When you finish

1. Zip `TEST_ROOT` (without any API key or trace that contains one) and send back `results/results.csv`, `results/summary.md`, the `screenshots/` folder and `logs/`.
2. Record the candidate: plugin version shown in Help, QGIS version, OS, provider and model, free or paid plan, proxy or VPN, date.
3. Do **not** close a GitHub issue because a row passed here; issues are closed on a hand-verified pass of their own row.
