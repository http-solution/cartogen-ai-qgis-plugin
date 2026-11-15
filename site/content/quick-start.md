---
description: Connect a model provider and run your first request in Cartogen AI.
---
This takes about five minutes. You need the plugin installed ([Install](@install)) and either an API key or a local Ollama server.

## 1. Open the panel

Click the **Cartogen AI** toolbar button, or use the **Plugins** menu. The panel is a dock: drag it to float it or dock it left or right. The first time, a short welcome dialog asks your role, QGIS experience and preferred answer style. It is optional (**Skip for now**), and the answers are saved as a plain `user_profile.md` in your QGIS profile folder that you can edit.

## 2. Choose a provider

Click **⚙ Settings** in the panel header.

| Provider | Key | Notes |
|---|---|---|
| **OpenRouter** | https://openrouter.ai/keys | Has a free tier that covers many models; a good default if you have no other key. |
| **Google Gemini** | https://aistudio.google.com/apikey | Free and paid plans differ in which models they allow. |
| **Ollama** | none | A local server: enter its endpoint URL. Nothing leaves your machine. |

Paste the key. The model list refreshes when you tab out of the field. Leave the model on **Auto** and the plugin sends simple requests to a cheaper, faster model and complex multi-step ones to a stronger model (Ollama always uses the model you pick). Click **OK**. You can switch providers later from the small dropdown in the panel header.

Keys are stored in QGIS's encrypted Authentication Manager. If it is unavailable, the key is held in memory for the session only and Settings warns you; it is never written to disk in plain text. See [Security overview](@security/overview).

<div class="callout"><strong>Providers offered</strong>
Settings lists OpenRouter, Gemini and Ollama, plus a "Cartogen API" entry that is a stub: no hosted gateway is deployed yet, so it cannot be used. OpenAI and Claude clients stay in the code but are not offered, because they were never tested.
</div>

## 3. Open the sample data (optional but recommended)

The repository ships a tiny synthetic project, `docs/release_smoke_assets/inputs/smoke_start.qgz`, with seven layers around Amman. It is the same data the [live test pack](@development/live-testing) uses, so you can compare your results with documented ones. Use a copy, not the original.

## 4. Send a request

Type in the chat box and press Enter. Good first requests:

- *List all layers in the project.* (Answered in the panel without a model call.)
- *Buffer smoke_points by 500 meters and add the result as smoke_points_buffer_500m.*
- *Rank the three hub candidates in smoke_hubs by average distance to the points in smoke_points.*
- *Apply a visible multicolor stretch to smoke_dem using its real pixel-value range.*

## 5. What you will see

1. **A task preview, sometimes.** If your request matches a task in the [task register](@reference/task-register), the panel shows the exact prompt it is about to send and why (which task, how confident, what you will get). Reply "yes" to send it, type your own wording to send that instead with nothing added, or "cancel".
2. **A plan strip** for multi-step requests, with progress and retry.
3. **Tool-call steps** listed under the reply (for example "Optimal hub siting"). Expand **Details** to see arguments and errors. A step that failed is marked and quoted, and the reply is checked against it.
4. **A confirmation card** before anything destructive (removing a layer, editing an attribute table in place). Only your click approves it.
5. **A footer** with what the request used (calls and tokens). **Stop** cancels a running request.

## Where to next

- [User guide](@user-guide): attachments, project memory, sensitive points, dashboards, monitoring.
- [Troubleshooting](@troubleshooting) if something does not behave.
- [The agent loop](@architecture/agent-loop) for what happens between your request and the answer.
