# rc34 hand-verification sheet

Zip: `cartogen_ai_v1.16.0-rc34.zip` from the `cartogen-ai-v1.16.0-rc34` pre-release. Check it against `SHA256.txt` on the release page before installing. Use a **fresh QGIS 4.2 profile** and the rc22 fixtures (`docs/release_smoke_assets/inputs`).

This sheet covers only what changed since rc24. For a **complete** hand test (every category, all input files, every output path and screenshot rule) follow `docs/FULL_LIVE_TEST_rc34.md` and its helper `tools/live_test_pack.py`; this sheet's rows are included there as `RC34-*`.

None of what is in this sheet has been hand-tested. CI was green on every build from rc25 to rc34, including the live checks in QGIS 4.2.2 against a local test server, but no real model provider or API key has been used through the QGIS network path by anyone except the field reports quoted below. Mark each row **PASS / FAIL / NOT RUN**; for a FAIL write what you saw and keep a screenshot.

**Data and destination.** Every prompt goes to the model provider you configured, together with what the agent reads to answer it (layer and field names, counts, tool results, which can include coordinates). Run these rows only on the synthetic fixtures, with a provider you are authorised to send them to, and write the provider and model at the top of your results. If an egress card names a layer you did not expect, cancel it and report it. Nothing here authorises sending real or sensitive data anywhere. See `docs/RELEASE_LIVE_TEST_SCENARIOS.md`, section 1a.

**Never paste an API key into a report.** Where a row shows the last four characters of a key, write only those four.

**Keep QGIS's Network Logger panel closed** while a key is configured: while it is open, request headers, including the API key, appear in it on your own machine.

## What changed since the last sheet (rc24)

| Build | Change under test |
|---|---|
| rc25 | Settings offers only OpenRouter, Google Gemini, Ollama and the Cartogen API entry (a stub). The zip's folder is `cartogen_ai_plugin`. |
| rc26 to rc27 | Data fetches and the AI provider calls go through QGIS's network stack (proxy, authentication and SSL settings apply). |
| rc28 | Warning when an old `cartogen-ai` folder is installed next to this one. |
| rc29 | Replies cannot forge internal links; limits on remote data; smaller zip; diagnostics in the QGIS Message Log. |
| rc30 | Large downloads and the account client use QGIS's network stack; scripts refuse to run without isolation. |
| rc31 | No invalid menu category; temporary layers are checked; results in the Memory, Layer Sensitivity and account dialogs appear in a bar inside the dialog; layers redraw after score fields are written. |
| rc32 | A refused request shows the provider's reason code; a switch (`cartogen_ai/hosted_requests_via_qgis`) sends hosted AI requests the old way. |
| rc33 | A request that carries a body or a key follows redirects inside the plugin and keeps the key on the same site; redirects are logged (host names only). |
| rc34 | A refused Gemini request lists what each model answered and which key was sent; the retired `gemini-2.5-flash` is replaced by `gemini-3.8-flash` and `gemini-3.7-flash`; a zero-quota reply is returned at once and the next model is tried; a denied project stops the search. |

## 1. Install and first run

Remove any older copy first: delete a `cartogen-ai` folder from your profile's `python/plugins` directory if one exists (rc24 and earlier used that name), then restart QGIS.

| Row | Action | Expected | Result | Notes / evidence |
|---|---|---|---|---|
| I1 | Plugins > Manage and Install Plugins > Install from ZIP: pick `cartogen_ai_v1.16.0-rc34.zip`. Restart QGIS. | The plugin loads without a Python error. It is listed under the normal Plugins menu (not under Vector, Raster or Web). | | |
| I2 | Only if you still have an old `cartogen-ai` folder in the profile's plugins directory, leave it there and restart. | A warning at startup says two copies would load and tells you to delete the old one (rc28). NOT RUN if you have no old folder. | | |
| I3 | Open the Cartogen dock. Open Help. | "What's new" shows **rc34** and lists the rc34 items; the counts of tools and tasks are plausible. | | |
| I4 | Settings: the provider list. | Only OpenRouter, Google Gemini, Ollama (local) and the Cartogen API entry. No OpenAI, no Claude (rc25). | | |
| I5 | View > Panels > Log Messages. | A startup line appears in the plugin's tab with `plan_validation_gate`, `egress_gate_mode` and `persist_chat` and no Python traceback. | | |

## 2. Gemini through the QGIS network stack (first real-provider use)

Enter a Gemini API key in Settings and save it. QGIS may ask for its master password: enter it, and note whether it asked once or several times.

Write down: provider, model chosen in Settings (use **auto (recommended)**), whether the key's Google project is on the free or a paid plan.

| Row | Prompt / action | Expected | Result | Notes / evidence |
|---|---|---|---|---|
| G1 | NEW CHAT. "Hello." | A normal reply from the model. In Log Messages one `model_call` line with `outcome` not `provider_error`. | | |
| G2 | NEW CHAT. "List the layers in the project." | Answered in the dock without a model call (rc25), listing the fixture layers. | | |
| G3 | NEW CHAT. One real question that needs a tool: "How many features are in smoke_points?" | A count that matches the layer's feature count (open its attribute table to check). Count the `model_call` lines for the request: more than 4 is a finding. | | |
| G4 | **Free-tier key only, otherwise NOT RUN.** Settings: set the Gemini model to `gemini-3.1-pro-preview`. NEW CHAT. "Hello." | Within a few seconds, not after a minute: either a normal reply from a fallback model (the status line says the Pro model "has no quota on this plan, trying ...") or one short sentence saying the free tier has no quota for that model and what to do. **No** screenful of JSON. | | |
| G5 | Settings: set the model back to auto. Save a deliberately wrong key (change the last characters). NEW CHAT. "Hello." | An error that names the **provider's reason** (for example `Provider reason: ...` or `Google says: ...`), says how many characters the key sent had, shows only its **last four characters** and says where it came from (QGIS's saved credentials). The whole key never appears. | | |
| G6 | Put the correct key back. Repeat G1. | A normal reply again. | | |
| G7 | Settings model list for Gemini (open the dropdown). | Offers at least auto, `gemini-flash-latest`, `gemini-3.8-flash` and `gemini-3.1-pro-preview`. `gemini-2.5-flash` may still appear if Google's own model list returns it: that is expected, the plugin's built-in fallback no longer uses it. | | |
| G8 | If any request fails with 403 or 404 in G1 to G6: copy the whole error line (it lists what each model answered). | You can say from the line alone whether Google denied the project, a model is retired, or the reply did not come from Google (it then names the server). Write the line here, without the key. | | |

## 3. The sender switch (rc32)

Only needed if G1 fails with a 403 that G8 cannot explain.

| Row | Action | Expected | Result | Notes / evidence |
|---|---|---|---|---|
| S1 | Plugins > Python Console: `from qgis.core import QgsSettings` then `QgsSettings().setValue("cartogen_ai/hosted_requests_via_qgis", False)`. Restart QGIS. Repeat G1. | Hosted requests go through the Python `requests` library instead. Write whether G1 now passes. | | |
| S2 | Set the value back: `QgsSettings().setValue("cartogen_ai/hosted_requests_via_qgis", True)`, restart. | Back to the QGIS network stack. | | |

If S1 changes the outcome, that is the finding: report which of G1 passed with the switch off and failed with it on, with the error line.

## 4. Log lines (rc32 to rc34)

| Row | Action | Expected | Result | Notes / evidence |
|---|---|---|---|---|
| L1 | After any 401 or 403 in section 2, read the Log Messages tab. | A `provider_auth_refused` line with `status`, `sender=qgis` and `host` (a host name such as `generativelanguage.googleapis.com`). No key, header or body text. | | |
| L2 | Look for `http_redirect` lines around the same time. | Normally none. If one appears it shows `status`, `from_host`, `to_host`, `other_site` and nothing else. Report any you see. | | |
| L3 | Search the whole Log Messages panel for your key (use the last four characters, then the first four). | Nothing. A key anywhere in the log is a FAIL. | | |

## 5. Dialog notices and redraw (rc31)

| Row | Action | Expected | Result | Notes / evidence |
|---|---|---|---|---|
| D1 | Open the Memory dialog. Click **Export My Data**, choose a file. | A green bar inside the dialog says where it was exported. No pop-up box. It clears itself after a few seconds. | | |
| D2 | In the Memory dialog click **Clear Saved Chat**. | A **question** pop-up asks first (this one stays a pop-up). After Yes, a bar inside the dialog reports how many messages were deleted. | | |
| D3 | Trigger a failure in the Layer Sensitivity dialog (for example choose a name that matches two layers, if you can set that up). | A warning bar inside the dialog that stays until dismissed. NOT RUN if you cannot set it up. | | |
| D4 | Settings: save a Gemini key when QGIS's credential store is unavailable, if you can arrange it. | The pop-up about keeping the key for this session only still appears (it stays a pop-up on purpose). NOT RUN otherwise. | | |
| R1 | Use one of the tools that write a score field into a layer (severity index, presence gap, population in need; rc22 rows V1, J5 and V4 show prompts that use them), with a style already applied to that field. Run it a second time so the values change. | The map colours update to the new values straight away, without clicking refresh. NOT RUN if you cannot set up a layer styled on the field the tool writes. | | |

## 6. Downloads through the QGIS network stack (rc30)

| Row | Action | Expected | Result | Notes / evidence |
|---|---|---|---|---|
| W1 | Ask Cartogen to download local road data for a small area (the rc22 fixtures' area). | If the size is above the threshold in Settings, a confirmation card appears first. Progress is shown. | | |
| W2 | Start a download and press Stop part-way. | It stops promptly; no half-written file is left that looks complete. | | |
| W3 | Let one download finish. | The layer loads. | | |
| W4 | Disconnect the network mid-download. | An error saying the download was cut short, not a smaller file that opens as if complete. NOT RUN if you cannot do this safely. | | |

## 7. Lifecycle and package

| Row | Action | Expected | Result | Notes / evidence |
|---|---|---|---|---|
| P1 | Plugins > Manage and Install Plugins > Installed: untick Cartogen AI, tick it again, with the dock open and a chat on screen. | No Python error; menu and toolbar entries appear once, not twice; the dock opens. | | |
| P2 | Open the zip in an archive tool. | Top folder `cartogen_ai_plugin`; `LICENSE`, `metadata.txt` and `__init__.py` present; no hidden files, no `.pyc`, no `__pycache__`; about 1.5 MB. | | |
| P3 | Open `metadata.txt` from the zip. | `version=1.16.0-rc34`, `email=cartogenai@gmail.com`, no `category=` line, no percent sign anywhere. | | |

## 8. Rows carried over from the rc24 sheet

Run these from `docs/RC24_HAND_VERIFICATION_SHEET.md` and report them in this sheet's table:

- N3 (export overwrite card), N8 (print layout title and path), F3 (rotated canvas), V1 and J5 (severity looks).
- Q1 to Q3 (no invented layers or styles; stops guessing file paths).

Q4 and Q5 need a disposable PostGIS database: NOT RUN otherwise.

## Report back

The filled tables, plus a screenshot of any FAIL. Say which provider and model received your requests and whether the key's project is on the free or a paid plan. For any Gemini failure paste the **full error line** from the chat and the `provider_auth_refused` log line, with the key removed. Results go into a new issue titled "rc34 hand verification"; do not close any other issue from this sheet.

## Known not covered

- Whether a redirect on your network was the cause of any Gemini 403: the redirect handling (rc33) is tested in CI against a local server only. L2 shows whether one happens.
- Heavy raster operations still run on the main thread, so QGIS can freeze on a large raster (#221); a read-only database role is still the real protection for SQL.
- The Cartogen API entry is a stub (no hosted gateway exists); do not test it.
