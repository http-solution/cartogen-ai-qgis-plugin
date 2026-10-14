---
description: The layers of Cartogen AI, its main components and how a request travels from the chat box to a QGIS layer.
wide: true
---
Cartogen AI is a single Python package that QGIS loads as a plugin. It has no server and no build step. A request goes from the **dock panel** to an **agent** that talks to a **model provider** and calls **tools**; the tools use **PyQGIS and Processing** against your open project, and the results come back to the chat.

<div class="diagram-wrap">
<svg class="diagram" viewBox="0 0 900 470" role="img" aria-labelledby="d1t d1d" xmlns="http://www.w3.org/2000/svg">
<title id="d1t">Architecture of Cartogen AI</title>
<desc id="d1d">Five layers: the QGIS host, the plugin UI, the agent core, the tools, and the outside world of model providers and data services.</desc>
<style>
.bx{fill:var(--surface);stroke:var(--line);stroke-width:1.5}
.ac{fill:var(--accent-soft);stroke:var(--accent);stroke-width:1.5}
.am{fill:var(--amber-soft);stroke:var(--amber);stroke-width:1.5}
.tx{fill:var(--text);font:600 14px var(--font)} .sm{fill:var(--muted);font:12.5px var(--font)} .ar{stroke:var(--muted);stroke-width:1.5;fill:none;marker-end:url(#h)}
</style>
<defs><marker id="h" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="var(--muted)"/></marker></defs>
<rect class="bx" x="10" y="10" width="880" height="450" rx="14"/>
<text class="tx" x="26" y="34">QGIS 4.2 (host process)</text>
<rect class="ac" x="30" y="48" width="840" height="86" rx="10"/>
<text class="tx" x="46" y="72">UI: dock panel, settings, memory, help, dialogs</text>
<text class="sm" x="46" y="94">core/ui · chat formatting is Qt-free · Processing provider (hub siting, service area) registers with the Toolbox</text>
<text class="sm" x="46" y="114">The dock runs each request on a QgsTask worker thread and shows plan, steps, confirmations and the reply</text>
<rect class="ac" x="30" y="150" width="840" height="104" rx="10"/>
<text class="tx" x="46" y="174">Agent core (core/agent): the tool-calling loop</text>
<text class="sm" x="46" y="196">orchestrator · task matcher · tool router · prompt builder · history manager · usage tracker · scheduler</text>
<text class="sm" x="46" y="216">guards: loop guard · response guard · plan gate · egress gate · model view · output router · stray-fragment gate</text>
<text class="sm" x="46" y="236">state: spatial memory · chat persistence · results store · lineage · provenance · evidence folder</text>
<rect class="bx" x="30" y="270" width="410" height="104" rx="10"/>
<text class="tx" x="46" y="294">Tools (212)</text>
<text class="sm" x="46" y="316">@register_tool registry · one module per domain</text>
<text class="sm" x="46" y="336">dispatcher runs them on the GUI thread, or on the worker</text>
<text class="sm" x="46" y="356">for network-only and two-phase tools</text>
<rect class="bx" x="460" y="270" width="410" height="104" rx="10"/>
<text class="tx" x="476" y="294">QGIS APIs</text>
<text class="sm" x="476" y="316">qgis.core · Processing · QgsNetworkAccessManager</text>
<text class="sm" x="476" y="336">Auth Manager · QgsTask · layouts · print export</text>
<text class="sm" x="476" y="356">Isolated worker process for model-written scripts</text>
<rect class="am" x="30" y="390" width="840" height="56" rx="10"/>
<text class="tx" x="46" y="414">Outside the machine</text>
<text class="sm" x="46" y="434">Model providers: OpenRouter, Gemini (cloud) or Ollama (local)  ·  data: HDX, OSM, GDACS, USGS, UCDP, NASA, WorldPop</text>
<path class="ar" d="M450 134 L450 150"/><path class="ar" d="M235 254 L235 270"/><path class="ar" d="M665 254 L665 270"/><path class="ar" d="M450 374 L450 390"/>
</svg>
</div>

## The five layers

| Layer | Where | What it does |
|---|---|---|
| **UI** | `core/ui/` | The dock panel, settings, memory, layer-sensitivity, account and help dialogs. Runs on the GUI thread. Logic that can be tested without Qt (chat formatting, colour derivation, icons as SVG strings) is kept Qt-free on purpose. |
| **Agent core** | `core/agent/` | `CartogenAi` in `agent_orchestrator.py` is the tool-calling loop. It composes a tool dispatcher, a usage tracker and a history manager, and consults the task matcher, tool router and guards. See [The agent loop](@architecture/agent-loop). |
| **Tools** | `core/agent/tools/` | 241 tools, one module per domain, registered with `@register_tool`. See [Tools and routing](@architecture/tools). |
| **Providers** | `infrastructure/providers/` | One client per model provider behind a common interface. See [Providers and networking](@architecture/providers). |
| **Services and models** | `core/services/`, `core/models/`, `core/validators/`, `core/representation/` | Prompt refiner, tool router, response guard; confidence, sensitivity, egress-gate and plan-gate models; schema and P-code validators; the map representation planner. |

Cross-cutting: `core/logger.py` (structured, metadata-only logging), `core/exceptions.py`, `core/net.py` (HTTP through QGIS), `infrastructure/auth.py` (credentials), `infrastructure/settings_keys.py` (every `QgsSettings` key under `cartogen_ai/`).

## What is deliberately not here

- **No server.** Everything runs in your QGIS process, except an optional isolated subprocess for model-written scripts. `service/` in the repository is an unfinished prototype for a hosted gateway and is not part of the plugin or its tests.
- **No tier-gating.** One GPL v2 codebase; there is no licence-check logic.
- **No model hosting.** Requests go straight from your machine to the provider you configured, with your key. The "Cartogen API" provider is a stub.

## Design rules that shape the code

1. **Every module degrades without QGIS.** Each module that touches `qgis.core` has its own `QGIS_AVAILABLE` guard, so the unit tests run on a plain Python install. Real QGIS behaviour is covered by a separate live test job. See [Testing and CI](@development/testing).
2. **The model is untrusted input.** Its tool calls can carry attacker-influenced arguments (prompt injection, a hallucination, a malicious provider), so the dangerous capabilities are gated in code, not in the prompt. See [Security overview](@security/overview).
3. **Say what was and was not done.** Replies are cross-checked against the tool calls that actually ran; a guard stop always reports what finished. See [Guards](@architecture/guards).
4. **Metadata-only logging.** Logs never contain prompts, replies, tool arguments, results or coordinates.

## Where to read next

- [The agent loop](@architecture/agent-loop): one request, round by round.
- [Threads, tasks and Stop](@architecture/threading): what runs where, and why QGIS stays responsive.
- [Repository layout](@development/layout): the same structure as a file tree.
