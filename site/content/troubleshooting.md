---
description: Fixes for the problems people hit most with Cartogen AI, with the release that introduced each behaviour.
---
Everything the plugin logs goes to **View → Panels → Log Messages**, tab **Cartogen AI**. Logs record events and metadata only: never prompts, replies, tool arguments, coordinates or keys. Keep that panel open while you reproduce a problem.

## Install and start-up

| Symptom | Cause and fix |
|---|---|
| `ModuleNotFoundError: No module named 'cartogen-ai-qgis-plugin-…'` | You installed GitHub's "Source code (zip)". Install the release asset `cartogen_ai_v<version>.zip` instead. See [Install](@install). |
| A warning at start-up about an old install, or two copies of the plugin | An `cartogen-ai` folder from rc24 or earlier is still in `python/plugins/`. Delete it, restart QGIS. |
| `PermissionError: [WinError 5] Access is denied` while installing packages | A Windows file lock on a module QGIS already loaded. Close QGIS completely, install, reopen. |
| A feature reports a missing package | Optional dependencies are listed on the [Install](@install) page. A missing one disables only that feature. |

## Provider errors

| Symptom | Cause and fix |
|---|---|
| "No API key configured" | Add a key for the active provider in Settings. |
| Gemini answers 403 or "permission denied" | Since rc32 the message includes the provider's reason code (for example `PERMISSION_DENIED`, `API_KEY_INVALID`, `SERVICE_DISABLED`) and which key was sent (length, last four characters and where it was found, never the whole key). A refusal can come from the Google *project*, not the key itself; check it in Google AI Studio. |
| A model answers "quota 0" or 404 "no longer available" | The free tier has no quota for some models, and Google retires models. Since rc34 these are returned at once and the plugin moves to the next model in its fallback list. |
| 403 after a proxy or firewall in between | Fixed in rc33: a redirect used to drop the Authorization header; requests now follow redirects inside the plugin and keep the key on the same site. |
| You need the older request sender | Set the QGIS advanced setting `cartogen_ai/hosted_requests_via_qgis` to `false` (added in rc32; on by default). |

## During a request

| Symptom | Cause and fix |
|---|---|
| "[Agent stopped] … The request is NOT complete" | The loop guard ended a turn that repeated the same call, kept failing, or made no progress; the message says what was done. Reply "continue" or rephrase. Read-only research turns that gathered results are asked once to answer from them (rc35) before being stopped. See [Guards](@architecture/guards). |
| "Reached the tool-call limit" | The request needed many individual actions. Ask for it in bulk, or split it. |
| QGIS shows "Not Responding" during a long analysis | rc36 slices about 90 long loops into 50 ms pieces and moves hub siting, allocation and route ordering off the main thread, so the window should repaint and Stop should be heard. If it still freezes, note the prompt, how long, and the Log Messages lines. Python-implemented Processing algorithms (such as `gdal:slope`) deliberately run on the main thread, so a short pause there is expected. See [Threads, tasks and Stop](@architecture/threading). |
| The chat says a step "did not run" although the layer is there | Fixed in rc38 for `find_incident_reports`. Report any other tool that does it. |
| A layer of invented or "sample" records appeared | Fixed in rc39: the follow-up that asked the model for "representative sample data" is gone. Delete the layer and report the prompt. |
| A reply says something not in any tool result | Replies are footnoted when they name an identifier, figure or style no tool returned. That is a wording check, not a guarantee; verify anything consequential. |

## Data

| Symptom | Cause and fix |
|---|---|
| A CSV loaded with no location, or points are in the wrong place | Coordinate columns are detected by name (`latitude`/`lat`/`y`, `longitude`/`lon`/`lng`/`x`, or `wkt`/`geom`/`geometry`). Name the right columns, and pass `crs` if the data is not WGS84 degrees. |
| "No OCHA COD-AB dataset found on HDX" | Coverage is not universal. Use `fetch_geoboundaries` (broader, no P-codes). |
| `fetch_geoboundaries` fails with an HTTP error | The API itself was reachable in testing, so check your network or proxy; the Log Messages line names the host. |
| A URL download is refused: "non-public address" | The SSRF guard refuses loopback, private, link-local and metadata addresses at every redirect hop. See [Security overview](@security/overview). |
| An incident search returns nothing | An empty result means "nothing in these sources", not "nothing happened". The reply names the sources that answered, the ones that failed and the ones not searched. UCDP data is preliminary and weeks old; GDACS is global and filtered locally. |

## Collecting evidence for a bug report

1. Turn on **Record every model request and reply to a local folder (diagnostics)** and, if needed, the evidence folder in Settings. Both are off by default and store raw values, so check them before sharing.
2. Reproduce the problem and copy the relevant Log Messages lines.
3. Open an issue at [the tracker](https://github.com/http-solution/cartogen-ai-qgis-plugin/issues) with the plugin version (shown in Help), the QGIS version and the steps. Never paste an API key. Security problems go through [private vulnerability reporting](https://github.com/http-solution/cartogen-ai-qgis-plugin/security/advisories/new).
