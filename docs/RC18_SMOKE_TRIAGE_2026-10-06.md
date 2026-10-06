# rc18 hand test: triage (2026-10-06)

Source: `docs/RC18_LIVE_SMOKE_REPORT_2026-10-06.md` (as received, status "in progress"), with its screenshots and logs. Nothing here is hand-verified by me; the fixes ran offline only.

## What the tester ran and did not run
Ran: R1-R7, N1-N9 (partly in shared chats, so "NEW CHAT" was not always exact). **Not run:** V1-V10, T1-T8, J1-J17 and P1-P20 of the expanded sheet. The report lists the Yemen project, a non-GIS colleague and a database as unavailable. So the JIAF, IPC/INFORM/UNOSAT, plain-language and readability changes from the expanded sheet are **still unverified in a desktop session**.

## Findings and what was done (rc19)
| Id | Finding | Cause found | Action in rc19 |
|---|---|---|---|
| R2 | "Yes, proceed." to the task card was lost: "no pending operation" | The router card accepted only a fixed list of single words ("yes", "ok", "proceed"...). A natural phrase went to the model as a new message | Fixed: a reply made only of yes-words and fillers confirms; a reply with extra content is still an edit; destructive gates unchanged |
| R3 | Imagery: HTTP 416 after 357 s; the preview chose OSM task 19.02 with "most recent low-cloud scene" assumed and a forced MD report; after Stop a follow-up demanded `generate_spatial_report` | (a) ultralytics' downloader fails with 416 even after the partial file is deleted; (b) a named raster did not answer the imagery question, "report" as a verb was read as a deliverable; (c) the output-contract check ran after a stopped / failed turn | (a) plain whole-file download first, checked against the real asset; (b) raster evidence for the imagery slot, report noun/verb, named tool leads the chain; (c) no follow-up after Stop or a failed tool |
| R4 | Raster ramp right (35-214) but the Layers panel stayed grey until a later refresh | Legend was not refreshed | Fixed: legend refresh after the stretch (not hand-verified) |
| N1/N2 | Severity styling correct, but invisible under two rasters | The styled layer sat below the image and the DEM | Fixed: apply_humanitarian_look lifts the layer above rasters that cover it |
| N4/N5 | Wrong geography: a Damascus box (and [west,south,east,north] order) was used for a fixture in Jordan; a Syria layer was created; a report was forced | The model had no tool to read a layer's extent in degrees, so it recalled one; two tools take two different box orders. The forced report was the verb "report" | Added `get_layer_extent` (both orders named) and prompt rule 54; the verb fix above |
| N4 | STAC thumbnail cell showed `[Preview Image](http` and a document icon | The output-path matcher read the `s:/` of `https://` as a Windows drive and swallowed the URL | Fixed in chat_formatting; test added |
| R7/N8 | Legend lists smoke_dem though it is off the map | Not diagnosed. The legend already filters by map extent; QGIS may not filter rasters that way | **Open** |
| N3/N9 | A one-step plan for each export; an unrequested `auto_arrange_layer_order` | Model behaviour | **Open**, not harmful |
| N1 | The flood answer suggested Syria; project memory holds Damascus notes | Not proven; memory content is the likely input | **Open**; rule 54 does not cover prose |
| N8 | Right-edge coordinate labels clip against the legend frame | Not diagnosed | **Open** |
| Gate | Plugin Manager install, fresh profile, upgrade, two restarts, uninstall/reinstall | Not run | Still owed |

## Passed in the hand test (tester's evidence, not mine)
R1, R4 (range), R5, R6, R7 (scale), N1, N2 (calculation and continuation), N3, N4 (fifth tool call, table kept), N6, N7, N8 (title/path/PDF), N9.
