---
description: Home page of the Cartogen AI wiki (plain Markdown; the HTML site's home page uses styling GitHub's wiki would strip).
---
# Cartogen AI documentation

Cartogen AI is a spatial AI agent that lives inside QGIS ({{qgis_min}} and later, Qt 6). Describe a mapping or analysis task in plain language; it plans the steps, runs real operations against your open project, and shows every tool call, result and error instead of handing back a black box.

**Version {{version}}** · {{tools}} tools the agent can call · {{tasks}} tasks in the humanitarian task register ({{sections}} sections) · providers offered: OpenRouter, Google Gemini, Ollama (local) · {{tests}} automated test functions in {{test_files}} files · free and open source, GNU GPL v2.

> **Honest status.** The automated tests and the QGIS 4.2.2 live tests run on every change and pass, but only part of the plugin has been hand-tested by a person in desktop QGIS. Each release says plainly what was and was not verified; see [Status and open work](@project/status).

## Start here

- [Install](@install): get the release zip into QGIS, the right way, and avoid the one install mistake that breaks it.
- [Quick start](@quick-start): pick a provider, paste a key, and run your first request in five minutes.
- [User guide](@user-guide): the chat, task plans, project memory, attachments, destructive-action prompts and settings.
- [Tool reference](@tools/index): every tool, its arguments and what it does, generated from the live registry.
- [Troubleshooting](@troubleshooting)

## Understand how it works

- [Architecture overview](@architecture/overview): the layers, the main components and how a request travels through them.
- [The agent loop](@architecture/agent-loop): one request, round by round: model calls, tool calls, guards and the final answer.
- [Threads, tasks and Stop](@architecture/threading): how long analyses stay off the GUI thread and how Stop is heard.
- [Guards and honesty checks](@architecture/guards): what stops the assistant from inventing results or acting without consent.

## For humanitarian GIS teams

- [The six workflows](@humanitarian/workflows): rapid mapping, MSNA, logistics, severity (JIAF-style), allocation and anticipatory action.
- [Task register](@reference/task-register): the mapping tasks the plugin matches your request against, locally.
- [External data sources](@reference/data-sources): HDX, OpenStreetMap, GDACS, USGS, UCDP, NASA and more: what each tool reads, and what needs a key.
- [What leaves your machine](@security/privacy): exactly what is sent to a model provider, and the settings that limit it.

## For contributors

- [Repository layout](@development/layout)
- [Contributing](@development/contributing)
- [Testing and CI](@development/testing)
- [Releasing](@development/releasing)

## What it is, in one screen

- **Multi-provider.** OpenRouter, Google Gemini or a local Ollama server. You bring your own key; Ollama needs none and nothing leaves your machine.
- **Native to QGIS.** Tools use PyQGIS and Processing; two analyses are also registered as Processing algorithms, so they work in the Toolbox, the Model Designer and `qgis_process`.
- **Transparent.** A request that matches a known task shows you the exact prompt and why before anything is sent. Multi-step requests get a visible plan. Every tool call is listed; failures are reported, not hidden.
- **Careful by default.** Model-written Python runs in an isolated process with a restricted set of names. Destructive edits need a confirmation the model cannot give itself. Fetched URLs are checked against private addresses at every redirect.
- **Free and open.** GNU GPL v2 only. No account, no licence key, no tier-gating anywhere in the repository.

---
The source code, releases and issue tracker are in the [repository](https://github.com/http-solution/cartogen-ai-qgis-plugin).
