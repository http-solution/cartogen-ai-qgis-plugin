---
description: Documentation for Cartogen AI, the spatial AI agent for QGIS that plans, runs and shows its work against your open project.
---
<div class="hero" markdown="1">
<span class="pill">Version {{version}}</span>

# Cartogen AI

<p class="lede">A spatial AI agent that lives inside QGIS (version {{qgis_min}} and later, Qt 6). Describe a mapping or analysis task in plain language; it plans the steps, runs real operations against your open project, and shows every tool call, result and error instead of handing back a black box.</p>
</div>

<div class="facts">
<div class="fact"><b>{{tools}}</b><span>tools the agent can call</span></div>
<div class="fact"><b>{{tasks}}</b><span>tasks in the humanitarian task register, in {{sections}} sections</span></div>
<div class="fact"><b>3</b><span>providers offered: OpenRouter, Google Gemini, Ollama (local)</span></div>
<div class="fact"><b>{{tests}}</b><span>automated test functions ({{test_files}} files)</span></div>
</div>

<div class="callout warn"><strong>Honest status</strong>
The automated tests and the QGIS 4.2.2 live tests run on every change and pass, but only part of the plugin has been hand-tested by a person in desktop QGIS. Each release says plainly what was and was not verified; see <a href="@project/status">Status and open work</a>.
</div>

## Start here

<div class="cards">
<a class="card" href="@install"><b>Install</b><span>Get the release zip into QGIS, the right way, and avoid the one install mistake that breaks it.</span></a>
<a class="card" href="@quick-start"><b>Quick start</b><span>Pick a provider, paste a key, and run your first request in five minutes.</span></a>
<a class="card" href="@user-guide"><b>User guide</b><span>The chat, task plans, project memory, attachments, destructive-action prompts and settings.</span></a>
<a class="card" href="@tools/index"><b>Tool reference</b><span>Every tool, its arguments and what it does, generated from the live registry.</span></a>
</div>

## Understand how it works

<div class="cards">
<a class="card" href="@architecture/overview"><b>Architecture overview</b><span>The layers, the main components and how a request travels through them.</span></a>
<a class="card" href="@architecture/agent-loop"><b>The agent loop</b><span>One request, round by round: model calls, tool calls, guards and the final answer.</span></a>
<a class="card" href="@architecture/threading"><b>Threads, tasks and Stop</b><span>How long analyses stay off the GUI thread and how Stop is heard.</span></a>
<a class="card" href="@architecture/guards"><b>Guards and honesty checks</b><span>What stops the assistant from inventing results or acting without consent.</span></a>
</div>

## For humanitarian GIS teams

<div class="cards">
<a class="card" href="@humanitarian/workflows"><b>The six workflows</b><span>Rapid mapping, MSNA, logistics, severity (JIAF-style), allocation and anticipatory action.</span></a>
<a class="card" href="@reference/task-register"><b>Task register</b><span>{{tasks}} mapping tasks the plugin matches your request against, locally.</span></a>
<a class="card" href="@reference/data-sources"><b>External data sources</b><span>HDX, OpenStreetMap, GDACS, USGS, UCDP, NASA and more: what each tool reads, and what needs a key.</span></a>
<a class="card" href="@security/privacy"><b>What leaves your machine</b><span>Exactly what is sent to a model provider, and the settings that limit it.</span></a>
</div>

## For contributors

<div class="cards">
<a class="card" href="@development/layout"><b>Repository layout</b><span>Where everything lives and why the package is arranged the way it is.</span></a>
<a class="card" href="@development/contributing"><b>Contributing</b><span>Comments explain why, status is stated honestly, and judgement calls are flagged.</span></a>
<a class="card" href="@development/testing"><b>Testing and CI</b><span>The offline suite, the live QGIS job, lint, types and packaging checks.</span></a>
<a class="card" href="@development/releasing"><b>Releasing</b><span>The version-bump checklist and the release workflow.</span></a>
</div>

## What it is, in one screen

- **Multi-provider.** OpenRouter, Google Gemini or a local Ollama server. You bring your own key; Ollama needs none and nothing leaves your machine.
- **Native to QGIS.** Tools use PyQGIS and Processing; two analyses are also registered as Processing algorithms, so they work in the Toolbox, the Model Designer and `qgis_process`.
- **Transparent.** A request that matches a known task shows you the exact prompt and why before anything is sent. Multi-step requests get a visible plan. Every tool call is listed; failures are reported, not hidden.
- **Careful by default.** Model-written Python runs in an isolated process with a restricted set of names. Destructive edits need a confirmation the model cannot give itself. Fetched URLs are checked against private addresses at every redirect.
- **Free and open.** GNU GPL v2 only. No account, no licence key, no tier-gating anywhere in the repository.
