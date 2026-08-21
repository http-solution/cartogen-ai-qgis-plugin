# SAM-Family Imagery Feature Extraction — Specification

**Status: SHIPPED (2026-08-17), open decisions resolved with the spec's own recommended defaults**
(FastSAM only, hard-reject over `max_pixel_dimension`, no separate install-confirmation UI beyond
the existing qpip flow, library's own default checkpoint cache). `agent/tools/imagery_extraction.py`
implements the pipeline described below; `tests/test_imagery_extraction.py` covers every piece
listed as verifiable in §9. **What's NOT verified**: real segmentation quality, real CPU inference
timing, real memory behavior, and whether `gdal.Polygonize`'s actual output matches what the
implementation expects without adjustment -- §9's "cannot verify without a live QGIS session AND a
downloaded model checkpoint" list is unchanged by shipping this code; writing the implementation
doesn't substitute for that live pass. Do not treat this as fully proven until that pass happens.
The design below is left as originally written, as the record of what was specified, matching the
convention `PROMPT_REFINEMENT_LAYER_SPEC.md` established for a shipped spec.

---

## 1. Problem

`QGIS_AI_Agent_PRD.md` Phase 3 lists "semi-automated feature extraction from imagery" as **not
started**. `docs/SECURITY_AND_COMPETITIVE_REVIEW_2026-08.md` §B.2 found a real competitor filling
exactly this gap today: the **GeoAI** QGIS plugin does tree segmentation (DeepForest), water
segmentation, and Segment Anything (SAM 1/2/3)-based semantic/instance segmentation directly on
loaded imagery.

Cartogen AI has two adjacent but distinct capabilities today, neither of which is this:
- `fetch_building_footprints` — a **pre-computed baseline dataset** (Microsoft Global ML Building
  Footprints), not live extraction from whatever raster the user actually has loaded. Explicit in
  its own tool description that it can lag real conditions by months.
- The v1.2.0 changelog already **correctly rejected** asking a vision *LLM* to output precise
  polygon coordinates directly from an image — a known-unreliable pattern for work where geometric
  accuracy matters. That reasoning still holds and this spec does not reopen it.

What's missing: extracting real feature boundaries from a **specific raster the user actually has
loaded right now** (a fresh drone/satellite image, a scanned map, imagery `fetch_building_footprints`
doesn't cover well) — the gap a dedicated segmentation model closes, not a vision LLM.

## 2. Non-goals

- **Not training or fine-tuning a model.** Inference only, against a pretrained checkpoint.
- **Not class-specific detection** ("find all buildings" vs "find all trees"). SAM-family models are
  class-agnostic segmenters — they find object *boundaries*, not object *identities*. Attaching a
  semantic label the model didn't actually determine would violate `agent/prompts.py` rule 12's
  anti-fabrication stance applied to this codebase's own output, not just the LLM's text. If
  class-specific detection is ever wanted (tree canopy via DeepForest, matching GeoAI's other
  capability), that's a **separate**, later spec — a different model with a different problem shape,
  not a variant of this one.
- **Not a replacement for `fetch_building_footprints`.** Different tradeoff: that tool is instant,
  free, pre-vetted, but stale and building-specific. This tool is slower, resource-heavier, and runs
  on-demand against whatever's actually loaded, for whatever object boundaries are visually present
  — not just buildings.
- **Not GPU-required.** Every existing capability in this plugin runs on whatever machine the user
  already has (`Ollama` support is explicit evidence of this — see `docs/PRODUCT_TIERS.md`'s
  offline-first framing, and `docs/SECURITY_AND_COMPETITIVE_REVIEW_2026-08.md` §B.4 names this as a
  validated differentiator against GeoEdge AI's cloud-account requirement). This feature must degrade
  to CPU inference, not require CUDA.
- **Not attempting parity with GeoAI's full model suite** (DeepForest + water segmentation + SAM
  1/2/3 all at once). Scope to **one** segmentation path first; expand later if it proves useful.

## 3. Why this is architecturally different from every other tool in this codebase

Worth stating plainly rather than discovering mid-implementation:

- **Pure-Python discipline breaks here, deliberately.** `agent/tools/analysis_tools.py`'s own
  docstring states "pure-Python statistics throughout (no numpy/pandas/scipy)" as a deliberate
  convention. Running a real segmentation model requires `torch` (and transitively `numpy`) — there
  is no way to do real tensor-based inference without them. This is a scoped, acknowledged exception
  to that convention, not a drift away from it — every other tool in the codebase keeps the existing
  discipline.
- **A real binary dependency footprint**, not an API-key-only integration. Every provider this
  plugin talks to (OpenRouter, Gemini, OpenAI, Claude, Ollama) is a network client with no local
  binary weight. This is the first capability requiring a local model checkpoint file and a real ML
  runtime installed on the user's machine.
- **Unverifiable in this development environment.** Every other QGIS-dependent tool this session
  ships gets flagged as "needs live QGIS to verify" and stops there — a real QGIS install is a known
  gap this project already lives with. This feature adds a **second** unverifiable layer on top: even
  with QGIS, verifying this needs a downloaded multi-hundred-MB checkpoint and an actual inference
  run, which this session's own sandbox cannot do (no model download, no way to judge mask quality
  without seeing it against a real image). §9 states exactly what can and can't be checked before
  that live pass.

## 4. Model choice

| Option | Checkpoint size | CPU inference | Notes |
|---|---|---|---|
| SAM (ViT-H, Meta's original) | ~2.4GB | Minutes per tile — impractical | Rejected: too heavy for the offline/CPU-first positioning this plugin has built its whole identity around. |
| SAM (ViT-B, smallest official variant) | ~375MB | Still slow (tens of seconds to minutes per tile) | Same class of problem as ViT-H, smaller degree. |
| **FastSAM** (Ultralytics YOLOv8-based reimplementation of the same task) | ~144MB (small variant) | Seconds per tile on a modern CPU | **Recommended default.** Real package support (`ultralytics`), meaningfully faster on CPU than any true-SAM variant, "segment everything" mode fits an agent-driven (non-interactive-click) workflow directly. |
| MobileSAM (distilled) | ~40MB | Fastest of all options | Lower mask quality than FastSAM in published comparisons. Worth offering as an explicit lighter/faster opt-in for resource-constrained machines, not as the default. |

**Recommendation:** FastSAM as the default and only initially-supported model; MobileSAM as a
possible fast-follow if FastSAM proves too heavy in real user feedback. Full SAM (any variant) is out
of scope — the checkpoint size and CPU inference time both work against the offline-first
positioning this plugin has staked its differentiation on.

**Interaction mode:** FastSAM's "segment everything" (automatic mask generation, no point/box
prompts) is the only mode that fits a chat-driven agent — there's no live canvas-click interface for
the model to supply interactive prompts through. This produces every detected object boundary in one
pass, which then gets filtered (§5 step 4) rather than targeted.

## 5. Proposed tool: `extract_features_from_imagery`

```
extract_features_from_imagery(
    raster_layer: str,
    output_layer_name: str = None,
    min_area_m2: float = None,
    confidence_threshold: float = 0.4,
    max_pixel_dimension: int = 2048,
)
```

Pipeline:

1. **Load and bound the raster.** Find `raster_layer` (existing `_find_layer_by_name` pattern). If
   either pixel dimension exceeds `max_pixel_dimension`, refuse with a clear error rather than
   silently downsampling or silently hanging for minutes — the user should explicitly clip to an
   area of interest first (`buffer_analysis`/existing clip tools) rather than the tool guessing what
   subset they meant.
2. **Extract pixel data.** Read the raster band(s) into a numpy array via GDAL (already a hard
   dependency of this plugin through QGIS itself — no new dependency here).
3. **Run FastSAM inference** (`ultralytics` package) in automatic/"everything" mode. CPU by default;
   use CUDA automatically if `torch.cuda.is_available()`, no separate GPU-only code path to maintain.
4. **Filter results:** drop masks below `confidence_threshold`, and (after converting to real-world
   area in step 5) drop polygons below `min_area_m2` if given — SAM-family "everything" mode reliably
   produces a lot of noise-scale false positives on texture/shadow, worth filtering before ever
   showing the user a result, not leaving that for them to filter by hand.
5. **Convert each surviving mask to a vector polygon**, georeferenced back to the raster's real CRS
   using its affine transform (the same class of pixel-to-map-coordinate problem
   `georeference_image` already solves, reuse that pattern rather than inventing a new one). Prefer
   GDAL's own `gdal:polygonize` processing algorithm for the raster-mask-to-polygon step over
   hand-rolled contour tracing — matches this codebase's established "use the existing Processing
   algorithm, don't reimplement it" convention (`gdal:rastercalculator` for NDVI/change-detection,
   etc.).
6. **Add the result as a new vector layer** with a `confidence` attribute per feature (the model's
   own mask confidence score) — genuinely returned data, not a fabricated class label (§2's
   non-goal). No feature is ever labeled "building" or "tree" unless a future, separate
   class-specific model actually determined that.

## 6. Dependency & installation

New optional dependency group in `requirements.txt`, installed via the existing `qpip`-based
optional-dependency flow (`agent/deps.py`, same pattern as `matplotlib`/`pdfplumber`):
`ultralytics`, `torch` (CPU wheel by default — qpip installs whatever PyPI resolves for the user's
platform, no special GPU-wheel handling attempted).

**This dependency group is meaningfully heavier than any existing optional group** —
`matplotlib`/`pdfplumber` are tens of MB; `torch` alone is commonly 200MB+ even CPU-only, plus the
model checkpoint on first use. §10 open decision 3 covers whether that difference needs its own
confirmation step beyond the existing qpip install prompt.

## 7. Failure modes and fallbacks

- **Dependencies not installed:** same `QGIS_AVAILABLE`-style guard pattern this codebase already
  uses everywhere — return a clear error naming exactly what to install via qpip, don't attempt a
  degraded no-op result.
- **Raster too large** (§5 step 1): explicit error naming the actual pixel dimensions and the cap,
  telling the user to clip first — never silently downsample (a silent resolution change could make
  results look plausible while actually being computed against different ground truth than the user
  thinks).
- **No CUDA available:** silently falls back to CPU (§5 step 3) — this is the *expected*, primary
  path given the offline-first positioning, not a degraded fallback to apologize for.
- **Model checkpoint download fails** (first-use download, if `ultralytics` doesn't ship it
  bundled): clear error with the retry path, no partial/corrupt-state silent failure.
- **Zero features survive filtering:** a real, valid result (`{"success": true, "feature_count": 0,
  ...}`), not an error — matches this codebase's "empty result is different from failure" convention
  used elsewhere (e.g. `calculate_presence_gap`'s empty-match handling).

## 8. Prompt guidance (new rule, once built)

Mirroring rule 30's "never hand-write this via `execute_pyqgis_script`, use the tool" pattern: once
built, add a rule stating this tool's output is **class-agnostic** — the model must not describe
extracted polygons as "buildings" or any other specific object class unless the user's own framing
already established that context (e.g. they said "extract the building footprints from this drone
image" — reasonable to describe results that way in the response *text*, since that's relaying the
user's own framing back) — but the `confidence` field and the fact that it's a **boundary**
detection, not a **classification**, must be stated plainly, not glossed over.

## 9. What can and can't be verified before shipping

**Can verify in this environment, before any live QGIS pass:**
- Dependency-guard / graceful-degradation code paths (matches every other tool's tested pattern).
- The pixel-to-map-coordinate transform math (pure arithmetic, no model needed).
- Mask-filtering logic (confidence threshold, area threshold) against synthetic mask data.
- Raster-too-large rejection logic.
- Tool registration, schema, error-message correctness.

**Cannot verify without a live QGIS session AND a downloaded model checkpoint:**
- Actual segmentation quality/accuracy against a real image.
- Real-world CPU inference timing (the `max_pixel_dimension` default of 2048 is a starting estimate,
  not a measured value — needs live tuning).
- Memory behavior under `torch` + model load.
- Whether `gdal:polygonize`'s output shape actually matches what step 6 expects without adjustment.

This second category is a strictly larger unverifiable surface than any other feature shipped this
session, and should be stated to whoever reviews this spec as a real cost of building it, not
minimized.

**Confirmed live (2026-08-17), not hypothetical:** installing this dependency group while QGIS was
running failed with `PermissionError: [WinError 5] Access is denied` on
`...\dependencies\3.12\markupsafe\_speedups.cp312-win_amd64.pyd` — pip's `--target`-directory install
(the mechanism qpip uses) couldn't replace a `.pyd` file QGIS already had loaded, because `folium`
(already a base dependency, for `generate_html_dashboard`) shares the `jinja2`/`markupsafe` chain with
`ultralytics`'s own dependencies. This is a Windows OS-level file-lock constraint — no code running
inside the same already-loaded process can delete or overwrite a DLL/`.pyd` it currently holds open,
so this cannot be "fixed" by anything in this plugin's own code, only mitigated by clearer guidance
before and during the failure. Response: added an explicit "close QGIS before installing" warning to
this tool's own `ImportError` message, `requirements.txt`'s comment for this dependency group, and
`README.md`'s Optional dependencies section — all three now name the exact error and the exact fix
instead of leaving the user to troubleshoot a raw traceback cold. §10 item 3's "yes, explicit
confirmation" recommendation is reinforced by this, not superseded — a heavier, still-undone follow-up
would be a proper install-confirmation dialog in `ui/settings_dialog.py` rather than relying on error
text alone, left as a real open item, not claimed as done here.

## 10. Open decisions (need a call before implementation starts)

1. **Model choice** (§4): FastSAM as sole initial target, or offer FastSAM/MobileSAM as a `model`
   parameter from day one? *Recommend FastSAM only for v1* — a parameter for a choice nobody's asked
   for yet is speculative complexity; add MobileSAM later if FastSAM proves too heavy in practice.
2. **Area-of-interest requirement** (§5 step 1): hard-reject rasters over `max_pixel_dimension`
   (current proposal), or auto-downsample with a stated warning? *Recommend hard-reject* — per §7,
   silent resolution changes risk misleading results more than a clear upfront error costs in
   friction.
3. **Install-time confirmation:** does this dependency group's size (~200MB+ vs. `matplotlib`'s
   tens-of-MB) warrant an explicit "this will download ~200MB+ of ML libraries plus a model
   checkpoint on first use, continue?" confirmation beyond the existing qpip prompt, or is the
   existing flow sufficient? *Recommend yes, explicit* — matches the general principle (already
   established this session, prompt rule 29) of surfacing real costs plainly rather than burying them
   in a generic installer prompt.
4. **Where the checkpoint lives:** bundled nowhere (downloaded to a cache dir on first real use,
   matching how `ultralytics` itself typically handles this), or does this plugin need its own
   explicit cache-location setting? *Recommend the library's own default cache behavior for v1* —
   don't build settings UI for a location most users will never need to change.

## 11. Relationship to other roadmap docs

- `QGIS_AI_Agent_PRD.md` Phase 3: this spec is the concrete design for the "semi-automated feature
  extraction from imagery" line item, marked not-started there.
- `CHANGELOG.md`'s v1.2.0 entry: explicitly preserves that entry's rejection of the vision-LLM
  coordinate-guessing approach — this spec is the alternative it pointed toward, not a reversal of
  that decision.
- `docs/SECURITY_AND_COMPETITIVE_REVIEW_2026-08.md` §B.2, Tier 2 item 7: this spec is the direct
  response to that finding.
