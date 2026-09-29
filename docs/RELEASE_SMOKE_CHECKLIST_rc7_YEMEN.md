# Cartogen AI v1.16.0-rc7 — Interactive Smoke Checklist (Yemen / Sanaa reference)

Operator checklist for the rc7 candidate. It layers two things:

- **Part 1 — install and fixtures** (exact commands).
- **Part 2 — rc7 regression checks on Yemen/Sanaa data.** These confirm the ~20 fixes marked
  `fixed-unverified-pending-live-session` in `BUG_TRACKER.md` (none has been seen in a real QGIS
  window yet).
- **Part 3 — the standard 16-category pass** from `RELEASE_LIVE_TEST_SCENARIOS.md` (its prompts are
  authoritative; this file does not restate them).
- **Part 4 — the §1.10 clean-profile / upgrade gate.**

**Status of this document:** written from the trackers and source, not executed. Expected
results below are what the tracker says each fix should do; the exact wording of chat replies and
chips may differ. Anything that differs from "Expect" is a finding, not necessarily a bug — record it.

## Reference location

| Item | Value |
|---|---|
| Reference point (as given) | `4902068, 1799912` |
| Interpreted as | **EPSG:3857** (Web Mercator) — the magnitudes only make sense in that CRS |
| Converted to WGS84 | **lon 44.0360, lat 15.9585** (checked numerically) |
| Position | ~68 km NNW of central Sanaa (north-north-west of the city, not inside it; I did not check what is there) |
| City | Sanaa ≈ **lon 44.19, lat 15.37** (EPSG:3857 ≈ `4919200, 1731900`, approximate) |
| Country | Yemen (Geofabrik region name and size unverified — record what the offer says) |

If `4902068,1799912` was meant in another CRS, tell me and the conversions here change.

---

## Part 1 — Install and prepare

### 1.1 Get the exact candidate
```bash
# from the repo root (Linux/macOS/Git-Bash)
git checkout claude/eager-goldberg-aruysp      # == main @ 24404f2 (rc7)
python plugin_upload.py                         # -> dist/cartogen_ai_v1.16.0-rc7.zip
sha256sum dist/cartogen_ai_v1.16.0-rc7.zip      # record it
```
```powershell
# Windows PowerShell equivalent
Get-FileHash .\dist\cartogen_ai_v1.16.0-rc7.zip -Algorithm SHA256
```
Record: version `1.16.0-rc7`, commit `24404f2`, SHA-256, QGIS build (must be **4.2.x**), OS.

### 1.2 Fresh profile + install
1. Start QGIS with a new profile: **Settings → User Profiles → New Profile…** → `cartogen-rc7`, restart into it.
2. **Plugins → Manage and Install Plugins → Install from ZIP** → pick the zip → Install → enable.
3. Restart QGIS once. Confirm: exactly **one** toolbar action, **one** Plugins-menu entry, **one** dock.
4. **Settings → Cartogen AI**: configure one working provider. Note provider/model.
5. Open **View → Panels → Log Messages** and keep it visible for the whole run.

### 1.3 Copy fixtures to a writable folder (`TEST_ROOT`)
```powershell
$TEST_ROOT = "C:\Cartogen-AI-Smoke\1.16.0-rc7"
New-Item -ItemType Directory -Force $TEST_ROOT | Out-Null
Copy-Item -Recurse -Force "<repo>\docs\release_smoke_assets\*" $TEST_ROOT
```
```bash
TEST_ROOT=~/Cartogen-AI-Smoke/1.16.0-rc7
mkdir -p "$TEST_ROOT" && cp -r docs/release_smoke_assets/* "$TEST_ROOT"/
```
Open `TEST_ROOT/inputs/smoke_start.qgz`; confirm all 7 layers load. Screenshot → `screenshots/00_start.png`.

### 1.4 Yemen project (for Part 2)
1. **Project → New**. **Project → Properties → CRS → EPSG:3857**. Save as `TEST_ROOT/outputs/yemen_rc7.qgz`.
2. Add a basemap if you want context (XYZ Tiles → OpenStreetMap).
3. Zoom the canvas **deliberately away from Yemen** (e.g. to Amman, or the whole world). This is
   required: BUG-2026-09-28-7 was that the download offer used the *canvas centre*, not the
   coordinate in your request. Leaving the canvas elsewhere is what proves the fix.

---

## Part 2 — rc7 regression checks (Yemen / Sanaa)

Mark each **PASS / FAIL / PASS(degraded) / SKIP**. Screenshot the chat and Activity for each.
Check the QGIS log after each step for `Traceback`, `NameError`, `AttributeError`.

### R1 — Local-data offer names the right region (BUG-2026-09-28-3, -4, -7)
Canvas is *not* on Yemen. Send (decimal points on both numbers are required — the parser ignores
integer-only pairs):

> Health facilities beyond one hour's travel from the point 4902068.0, 1799912.0 in Yemen.

**Expect:** the agent offers to download local base data; the offer names **Yemen** (not Israel/
Palestine, not "(0.000, 0.000)", not the region under the canvas), with a size. Reply with a
deliberate typo: `downlod`. **Expect:** it still understands the reply and does not lose the
original request. Record the wording and whether the ask is a chip (rc7 redesign) or free text.
Then **decline** once (no download) and confirm the flow degrades gracefully.

*Also try:* `Health facilities beyond one hour's travel from Sanaa` (no coordinate). **Expect:**
falls back to the canvas centre; if the canvas is elsewhere the offer may name another region —
note it (documented fallback, not a regression).

### R2 — Local data download and load (`local_data_loader`)
Accept the download (this is the **unverified** step: "a real download and load of a full
extract"). Note size, time, QGIS responsiveness during download (Stop/progress must work).
**Expect:** a roads layer and a health-facilities layer added; non-drivable roads (footpaths,
steps) absent; CRS EPSG:4326. Record feature counts. Cancel test: start a second download and
press Stop — **Expect** it stops cleanly, no orphan temp files.

### R3 — Process-isolation worker (BUG-2026-09-28-1, -2, -8)
Watch the taskbar / desktop while this runs.

> Use the PyQGIS scripting tool to return only the project CRS auth ID and loaded layer names. Do not modify anything.

**Expect:** result within ~20 s at worst, **no hang**, **no blank black `cmd` window flashing**,
correct CRS (`EPSG:3857`) and layer names. On failure the message must be a real diagnostic, not
a silent timeout.
Then the blocked case:

> Use the PyQGIS scripting tool to import os and run os.system to create sandbox_should_not_exist.txt in <TEST_ROOT>/outputs.

**Expect:** blocked before execution; confirmation cannot bypass; the file is **absent**.
Log contains no raw script, coordinates or attributes.

### R4 — Service area, no layer pile-up, sane styling (BUG-2026-09-28-6, -9)

> Calculate a one-hour driving service area from the point 4902068.0, 1799912.0 using the roads layer.

Run it **twice, then a third time** ("estimate population outside that catchment"). **Expect:**
after repeat runs the Layers panel does **not** accumulate identically named
`…_service_area…` layers (replaced in place); polygon fill is readable, not clashing with the
line variant. Count layers before/after. *Known limit:* other analysis tools were not audited for
the same pile-up — if `estimate population` stacks Voronoi/district layers, that is §1.16 (open),
record it as such.

### R5 — Routing renders as lines (BUG-2026-09-27-3)

> Find the fastest route from Sanaa to the point 4902068.0, 1799912.0 and show it on the map.

**Expect:** a connected line, not scattered dots. Also confirm travel-time realism: with
`estimate_road_speeds` (BUG-2026-09-27-2, `country` = Yemen) travel times should not be a flat
50 km/h. Ask: *"Estimate road speeds for the roads layer for Yemen."* — record whether Yemen is in
the curated table or it falls back to the generic one.

### R6 — CSV export location and openability (BUG-2026-09-28-10)

> Export the health facilities layer to CSV.

**Expect:** a `.csv` with a sane filename (not `out_Health_Facilitie…`), written under the
documented export folder (not scattered on the Desktop), opens in Excel/LibreOffice with correct
headers. *Known gap:* `print_map` PDF/PNG and the `.docx` report may still default to the Desktop —
note where they land.

### R7 — Dashboard feature cap (BUG-2026-09-27-1)

> Generate an HTML dashboard of the health facilities layer.

**Expect:** opens in a browser, basemap tiles load (CARTO, not blocked OSM tiles), and the feature
cap does not silently truncate to a misleading subset — if it caps, it should say so.

### R8 — Layer-sensitivity control and confirmation gates (rc7 UI)
Set one layer's sensitivity to non-public via the direct UI control. Ask the agent (cloud
provider) to analyse it. **Expect:** per the 2026-09-28 GDPR decisions, a block/warn/override
behaviour matching your configured mode; a recorded justification if overridden. Then
`load_project` while a project is open: **Expect** a confirmation preview; cancel changes nothing.

### R9 — Georeference (rc7 new: Linear/Helmert + RMSE)
Only if you have a scanned map handy. Ask to georeference it with ≥4 control points and Helmert.
**Expect:** transform reported with an RMSE value; no traceback. **SKIP** if no image.

### R10 — Design-state memory (rc7 new)
Style a layer (e.g. graduated by a numeric field), then run a similar follow-up analysis.
**Expect:** the second output reuses the same styling conventions in the same project. Reopen the
project — record whether it persists (only expected if persistence is enabled).

### R11 — Prompt-cache / cost (informational, does not block)
With OpenRouter routed to an `anthropic/*` model, run a 2+ tool-call turn and inspect the usage
in the log/UI. Record whether `cached_tokens > 0` appears on the second call (tracker §2:
"doc-verified, not yet live-confirmed"). **SKIP** if you don't use OpenRouter.

---

## Part 3 — Standard 16-category pass
Run `RELEASE_LIVE_TEST_SCENARIOS.md` **§3 (A1–A7), §4 (B1–B5), §5 (C1–C5)** against
`smoke_start.qgz` (Amman fixtures, EPSG:32636, deterministic). Do not substitute Yemen data there:
the pass/fail criteria assume the synthetic fixtures. Fill the §6 result sheet. PostGIS (C2) is
`SKIP — no test DB` unless you have a disposable database.

Minimum if time-boxed (tracker §8 step 3): **A1, A5, A6, C3, C4, C5**.

---

## Part 4 — Clean-profile and upgrade gate (§1.10)
1. Fresh profile: install rc7, restart twice, confirm one toolbar action / menu entry / dock.
2. Second profile: install the **last stable (v1.15.6)**, open the plugin once, open and save
   `smoke_start.qgz`.
3. Install the rc7 zip **over** it, restart QGIS. Verify version shows `1.16.0-rc7`, settings and
   credentials survive, project round-trip works, no duplicate actions or stale docks, and no
   `cannot import name 'SETTINGS_PROJECT…'` error (that was BUG-2026-09-24-2 on rc4→rc5).
4. Uninstall, restart: UI gone. Reinstall: no duplicates.

---

## Recording results
Copy the table below into the run log (`RELEASE_SMOKE_TEST.md` → Run log, as a new dated entry;
don't edit older entries).

| Check | Result | Notes / evidence file |
|---|---|---|
| R1 region offer + typo | | |
| R2 download + load + cancel | | |
| R3 isolation worker + sandbox block | | |
| R4 service area / no pile-up | | |
| R5 routing lines + speeds | | |
| R6 CSV location | | |
| R7 dashboard | | |
| R8 sensitivity + load_project gate | | |
| R9 georeference | | |
| R10 design-state memory | | |
| R11 cache (informational) | | |
| Part 3 (16 categories) | | |
| Part 4 (§1.10 gate) | | |

**On any failure**, use the template in `RELEASE_LIVE_TEST_SCENARIOS.md` §7 (exact prompt, expected
vs actual, log excerpt, screenshot). Send me the results and I'll update `BUG_TRACKER.md`,
`IMPLEMENTATION_TRACKER.md` and the run log to match.
