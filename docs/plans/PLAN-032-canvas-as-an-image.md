# PLAN-032: the model sees the map (master list RM-B)

Status: in progress

## Goal
A user can ask "what is wrong with this map" and the model looks at the actual picture. Today `inspect_canvas_visually` returns the canvas as base64 text inside a tool result, which a model reads as hundreds of thousands of tokens of text, not as a picture (`docs/ROADMAP_AUDIT_2026-10-27.md`, finding 1). The five chat clients already carry image parts for user attachments, so the gap is plumbing.

## Scope
In:
1. A capture that renders the current canvas (optionally a chosen extent) to a PNG capped at about 1,280 pixels on the long edge, and adds it as an image part of the next message, with the legend text and the list of visible layers as text beside it.
2. A button in the chat and a tool the model can call; both use the same function.
3. A per-provider flag for vision support. Providers without it get the legend and layer list as text and a one-line reason.
4. **Privacy:** the egress gate applies. When a layer tagged RESTRICTED or SENSITIVE is visible, a capture bound for a cloud model asks first, exactly as an export does today (PLAN-011).
Out: an automatic look-fix-look loop (a follow-up once the capture is proven); video; region drawing tools beyond a rectangle.

## Acceptance
1. Offline: the message built for each client (OpenAI-style and Claude) contains an image part and the two text parts, in that order.
2. CI live: rendering a project with three layers gives a PNG that is not blank and within the size cap; a project with a protected layer visible returns the confirmation card, not the image.
3. Hand (owner), on at least Gemini and Claude: "what is wrong with this map" names layers that are visible in the picture; the same on a provider without vision gets the text fallback.
Not verified by this plan: a live vision call on every provider. The audit read the Claude conversion and the OpenAI-style request shape only.

## Guard tests
To be written: `tests/test_canvas_capture_message.py` (message shape per client), `tests/test_canvas_capture_live.py` (render and gate).

## Rollback
The button and the tool are removed from the registry; `inspect_canvas_visually` stays as it is.

## Status log
- 2026-10-28: plan written. No code.
- 2026-11-01 (owner said go to step B): built the model-callable half. `inspect_canvas_visually` (kept under its name, so the router phrases, the schema snapshot and the existing tests stay) now renders the canvas off-screen at 1,280 pixels at most, optionally the extent of a named layer (`extent_layer`), flags a blank render, and returns the legend and visible layers as text; if the off-screen render is unavailable it falls back to the old plain screenshot. The agent loop (`_detach_canvas_image`, `_add_image_messages`) takes the base64 out of the tool result and sends it as an image message after the round's tool messages, with the legend text and the layer list as the two text parts, in that order (acceptance 1, offline, for the OpenAI-style shape and the Claude conversion); only the newest picture is kept. A model that cannot take pictures (a name heuristic: Gemini, Claude and OpenAI always; OpenRouter, Ollama and the hosted client by model name; the CLI bridges never) gets the text and a one-line reason. Privacy: `egress_gate.VISIBLE_LAYER_TOOLS` makes the picture count as touching every VISIBLE layer; with the gate on, a visible RESTRICTED or SENSITIVE layer blocks it to a cloud model until the user confirms (offline test of the decision; the confirmation card itself is the existing gate's, not re-tested here). NOT done: the chat button (UI, next slice), the live render acceptance (written, CI's first run), any live vision call (acceptance 3 needs a person and keys), `run_steps` inner calls (picture not detached).
