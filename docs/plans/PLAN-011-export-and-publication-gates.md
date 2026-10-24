# PLAN-011: export and publication gates

Status: in progress

## Goal
Make "this map can leave the building" a checked state instead of an accident. Today (read in the code on 2026-10-24):
- `export_layout` (`layout_item_tools.py`) has no sensitivity check at all: a layout whose map shows a SENSITIVE or RESTRICTED layer exports with no note. The older data exports (`export_tools.py`) at least append the advisory `export_warning_for`.
- The only publication check is `map_qa` on the CARTOGRAPHY_READY to PUBLICATION_READY step of `advance_dataset_status`. It runs only when the caller passes `layout_name` (otherwise it falls back to a free-text note), it tests only the four mandatory elements and the one layer's tag, and nothing forces a layout through that step before `export_layout` or `create_print_layout` writes a PDF. So the check is real but optional, and a direct export bypasses it.
- The layout metadata is title, CRS and scale (`MAP_INFO`) and the AI-disclaimer footer. There is no data source and version line, no data date, no boundary or data-sensitivity disclaimer (`HUMANITARIAN_CARTOGRAPHY_STANDARDS.md` section VIII says these are mandatory; it recorded the gap on 2026-09-03 and it is still open).

## Scope
Three phases, each its own pull request. Each ends in something that works on its own; stop after any of them.

**Phase A: close the bypass without changing who may export (advisory, no policy decision needed).**
1. `export_layout` and the export inside `create_print_layout` list the layers their map items draw, and append one note per RESTRICTED or SENSITIVE layer (the existing `protected_layer_notes`, same rule as every other export). Result carries `protected_layers`.
2. The same two exports run the mandatory-element check (title, legend, scale bar, north arrow) on the layout and report `missing_elements`, so a stripped-down layout says so instead of exporting silently.
3. Both are warnings only; nothing is blocked. Tests: offline for the pure selection and wording, live for a real layout holding a tagged layer.

**Phase B: a real gate (needs your decisions below).**
4. Exporting a layout whose map draws a SENSITIVE or RESTRICTED layer asks for confirmation through the same confirm-card mechanism the overwrite preview already uses (not a hard block; `confirmed` is set only by the user's button).
5. `export_layout(purpose="publication")`: runs `map_qa` for that layout and the layers it draws; refuses unless it passes or the user confirms with a stated reason, which is written next to the file (provenance sidecar). Without `purpose`, behaviour is Phase A only.

**Phase C: the metadata block (needs your wording).**
6. `create_print_layout` gets a structured sources line (name, publisher, version or date for each layer drawn, read from layer metadata where present, else shown as "source not recorded") and a "Map prepared" date.
7. A boundary and data-sensitivity disclaimer in the footer, with the text taken from a setting. The default is a neutral generic sentence; the organisation-specific wording (for example the standard UN boundary text) is yours to supply, not mine to invent.

Out: OCHA template and branding profiles, accessibility and multilingual typography, product page-size profiles, file-naming and DPI presets, locator map and graticule defaults, reviewer sign-off workflow, render-based QA. Those are the feature set in the second half of the audit and need their own plan after A to C.

Owner decisions (2026-10-24): (1) a protected layer in an export asks for confirmation on the confirm card, not a hard block; (2) the publication check runs only when `purpose="publication"` is asked for, not on every PDF; (3) the boundary disclaimer comes from a setting with a neutral default, on by default; the organisation's exact wording is supplied later.

## Acceptance
1. Phase A: exporting a layout that draws a SENSITIVE layer returns `protected_layers` and a note, and a layout with no legend returns `missing_elements`; both have a failing-without-the-fix test.
2. Phase B: the confirm card appears and the export does not run until confirmed; a `purpose="publication"` export of a failing layout is refused with the reason, and a confirmed one records its reason.
3. Phase C: a layout shows a sources line and a prepared date without any argument, and the disclaimer text comes from the setting.
4. Nothing is called hand-verified until you have exported a real layout; the export tools are CI-live only.

## Guard tests
To be listed per phase. Existing ones that must keep passing: `tests/test_qa_checklist_tools.py`, the layout live tests (`tests/test_layout_items_render_live.py`), `tests/test_dataset_status*.py`.

## Rollback
One pull request per phase; revert the phase. Phase B is behind the confirm card and the `purpose` argument, so a revert changes no stored data.

## Status log
- 2026-10-24: plan written after reading `export_layout`, `layout_tools.py`, `models/dataset_status.py` and `models/sensitivity.py`. No code changed. Owner answered the three decisions (recorded in Scope). Phase A starts on the owner's go.
- 2026-10-24: plan merged as #392. Phase A built (`layout_export_checks.py`; wired into `export_layout` and `create_print_layout`): exports now report protected layers drawn and missing mandatory elements as warnings. Phase B and C not started. Not hand-tested.
- 2026-10-24: Phase A merged (#393). Phase B built: `gate_export` / `build_time_preview` in `layout_export_checks.py`; `export_layout` gains `purpose` and `override_reason`; `create_print_layout` gains a UI-only `confirmed`. What the publication check tests: the four mandatory elements plus the map and any protected layer drawn (not per-layer dataset status; a layer without a tracked status is not blocked). The sensitivity card also covers `create_print_layout`'s own export, checked before anything is built, using the layers ticked in the project. Phase C not started. Not hand-tested.
