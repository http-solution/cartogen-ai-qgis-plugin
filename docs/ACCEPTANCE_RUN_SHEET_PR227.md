# Acceptance run sheet: cost-and-routing branch (PR #227)

Purpose: the first real test, with a real model, of what PR #227 added: the cost measurement, the loop guard and token budget, the job queue, `run_steps` and the 11 pre-built chains, input discovery, `fetch_dem`, and the evidence folder. Everything so far was tested offline or in headless QGIS Docker only. **Nothing here has been run by the developer.**

## Before you start

1. Install the rc23 zip built from the current `main` (PR #227 is merged, so this is the same build as the hand-verification sheet uses). Fresh QGIS profile, QGIS 4.2.x.
2. Settings: choose ONE cheap model and keep it for every run (write it in the log). Turn ON **Save an evidence folder for each request**. Leave the token budget at the default (450,000). Leave the tool-call cap at 20.
3. Save the project first so the evidence folders land next to it (otherwise they go to the QGIS profile `cartogen_ai/exports` folder).
4. Network: the OSM, HDX and the Copernicus DEM downloads need internet. Note the time of each run; OSM data changes.
5. Do not retry a failed run silently. Record it, then retry once and record that too.

## How to run each scenario

New chat, new project each time. Paste the scenario text exactly. Answer any confirmation card with the card's own button. Do not give hints. Let it finish or stop on its own. Then fill the log table below, open the evidence folder, and do the independent checks.

## Log (one row per run)

| Run | Scenario | Model | Finished? (done / stopped by guard / budget / error) | Model calls | Tool calls | Footer tokens | run_steps used? (y/n, how many steps) | Chain offered? | Evidence folder | Result vs independent check | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | marib |  |  |  |  |  |  |  |  |  |  |
| 2 | districts |  |  |  |  |  |  |  |  |  |  |
| 3 | aden |  |  |  |  |  |  |  |  |  |  |
| 4 | taizz |  |  |  |  |  |  |  |  |  |  |
| 5 | highway |  |  |  |  |  |  |  |  |  |  |
| 6 | combined queue (all five pasted as numbered jobs in one message) |  |  |  |  |  |  |  |  |  |  |

Where to read the numbers: the turn footer under each reply shows tokens; the QGIS Python console / Log Messages panel (tag `Agent`) has `model_call` lines (call index, input / cached / output tokens, tools offered) and `tool_call` lines. `steps.jsonl` in the evidence folder has every call with its real arguments. If the footer shows no cached-token figure, write that down: it means the provider does not report it.

## The five scenarios and their independent checks

### marib

```
I need an urgent health access assessment for displaced families around Marib city. Query OpenStreetMap via the Overpass API for all operational hospitals, clinics, and pharmacies within the Marib area (bounding box around 15.35° N, 45.20° E to 15.55° N, 45.45° E), along with the primary and secondary road network. Create a 15-minute walking distance buffer (1.2 km) and a 30-minute buffer (2.5 km) around each health facility using a metric projection (UTM 38N / EPSG:32638). Symbolize the zones with an accessible green-to-amber color ramp and report the total square kilometers covered by walking access.
```

Independent checks (do these yourself, do not ask the plugin):
- Layer counts per facility type match an independent Overpass Turbo query for the same bounding box (note the query date).
- The 1.2 km and 2.4 km (30-minute) buffers: measure one buffer's radius with the measure tool in a projected CRS; it must be 1200 m / 2400 m, not degrees.
- Any population or area figure in the reply: recompute with the QGIS field calculator or Statistics panel.

Also record: did it stop early and say exactly which parts were done? Did anything claim a result no tool returned?

### districts

```
Download the official UN OCHA Yemen Administrative Boundaries (COD-AB) GeoJSON directly from the Humanitarian Data Exchange (HDX) API or OCHA GitHub endpoint. Extract the District level (Admin 2) polygons. Filter for all districts in Hadramawt and Al Mahrah governorates. Calculate the exact geodesic land area in square kilometers for each district, rank them from largest to smallest, generate label centroids, and display a graduated map based on surface area.
```

Independent checks (do these yourself, do not ask the plugin):
- District count for the two governorates matches the HDX file (open the downloaded file and filter by hand).
- Pick three districts: compare the reported km² with `$area` set to ellipsoidal in the field calculator (tolerance 0.5%).
- The ranking order matches a sort of that field.

Also record: did it stop early and say exactly which parts were done? Did anything claim a result no tool returned?

### aden

```
We are designing a water distribution plan for Aden peninsula. Extract all mapped water infrastructure points (wells, water points, water towers, public taps) from OpenStreetMap for the Aden urban area. Then extract all residential and commercial land-use polygons. Generate a 500-meter service buffer around every water point, dissolve them, and perform a spatial difference against the residential land use to highlight unserved urban neighborhoods. Report the total area of unserved residential zones in hectares.
```

Independent checks (do these yourself, do not ask the plugin):
- Water-point count matches an independent Overpass Turbo query.
- A 500 m buffer measured in a projected CRS is 500 m.
- Uncovered area in the reply matches the area of the difference layer (Statistics panel, ellipsoidal).

Also record: did it stop early and say exactly which parts were done? Did anything claim a result no tool returned?

### taizz

```
A field team wants to establish a mobile clinic near Taizz at coordinates 13.578° N, 44.015° E. Create a 5 km circular study area centered on that point. Query a public elevation source (like OpenTopography SRTM API or AWS Terrain tiles) for this bounding box. Calculate slope in degrees. Classify the terrain into three categories: Flat (< 5°), Moderate (5°–15°), and Dangerous/Steep (> 15°). Flag whether the target GPS coordinate falls within safe flat terrain, and generate 10-meter vector contour lines across the study area.
```

Independent checks (do these yourself, do not ask the plugin):
- The study area radius measured in a projected CRS is 5 km around 13.578 N, 44.015 E.
- The DEM layer's properties show source Copernicus GLO-30, about 30 m pixel; the reply must say it is a surface model, not bare earth, and must name the attribution.
- Slope class areas: sum of the three classes equals the study area (+/- 1%). Spot-check one cell against a hand calculation from neighbouring heights.
- Contour interval is described as spacing, not accuracy.

Also record: did it stop early and say exactly which parts were done? Did anything claim a result no tool returned?

### highway

```
Extract the primary coastal highway (N1 / Route 99) from Bab al-Mandab north to Mocha from OpenStreetMap. Assume three hypothetical checkpoint delays at the following coordinates: [12.650, 43.480], [13.020, 43.340], and [13.310, 43.250]. Generate a 2.5 km security exclusion zone around each checkpoint. Split the highway geometry by these exclusion zones, style the compromised road segments in red and clear segments in green, and compute the total remaining continuous passable road length in kilometers.
```

Independent checks (do these yourself, do not ask the plugin):
- Total highway length, passable length and longest passable segment: measure with the field calculator (`$length`, ellipsoidal) on the split layer. TOTAL PASSABLE and LONGEST CONTINUOUS must be two different numbers unless one zone sits at the end.
- Each exclusion zone radius measured in a projected CRS is 2.5 km.
- Compromised segments are red, passable green, and the three checkpoints are where the prompt says.

Also record: did it stop early and say exactly which parts were done? Did anything claim a result no tool returned?

## Combined queue (run 6)

Paste the five scenarios as a numbered list in one message. The plugin should show the proposed split first and wait for confirmation, then run one job at a time with its own budget. A job that fails or stops must not stop the others, and the summary must say which jobs finished. Record the order, per-job result, and total tokens.

## What decides the next step

- **Round trips:** compare model calls per scenario with the rc22 figures (median 2 tool calls, p90 11, max 15 per request, about 22-26k tokens per call). Did `run_steps` or a chain cut calls? If models never use them, say so; that is a result.
- **Budget:** did any run hit the 450,000 budget? Was the stop message honest about what was finished? If no run came close, the default can be tightened; if several hit it before finishing, it is too low.
- **Cache reporting:** does the provider report cached tokens? (yes / no / unknown)
- **Chains:** when a chain was offered, did the model follow the step order and fill the slots correctly? Note every slot it got wrong.
- **Correctness:** any independent check that disagrees with the plugin is the most important finding: report it first.
- **Evidence folder:** does it contain `summary.md`, `steps.jsonl`, `manifest.json`, copies of written files and a screenshot? Is anything missing or unexpectedly sensitive?

Send back the filled log plus the evidence folders (or at least `summary.md` and `steps.jsonl`; check them for sensitive values first).
