---
description: Where everything lives in the repository, and why the package is arranged the way it is.
---
The repository is a **single tree**: one GPL v2 codebase with no second copy to keep in sync (an earlier version maintained two parallel trees; see the `[1.4.0]` changelog entry). The plugin has no build step; the only artefact is the release zip.

```text
cartogen-ai-qgis-plugin/
├── __init__.py            plugin entry point (classFactory); bootstraps the namespace package
├── plugin_main.py         initGui / unload, toolbar action, dock, Processing provider
├── metadata.txt           QGIS plugin manifest, with the embedded changelog
├── plugin_upload.py       builds the release zip (top folder cartogen_ai_plugin)
├── src/cartogen_ai/       the code (below)
├── tests/                 unit tests (no QGIS needed) and *_live.py tests (need QGIS)
├── docs/                  living references, trackers, dated reports, release_smoke_assets, images
├── tools/                 developer scripts (live test pack, audits, task derivation)
├── site/                  this documentation site (generator, theme, authored pages)
├── service/               unfinished hosted-gateway prototype; NOT part of the plugin
├── branding/              logos and brand guidelines
└── .github/workflows/     tests, release, Pages
```

## `src/cartogen_ai/`

```text
core/
├── agent/                 the agent core
│   ├── agent_orchestrator.py   CartogenAi: the tool-calling loop
│   ├── tool_dispatcher.py      GUI-thread bridge for tools
│   ├── usage_tracker.py, history_manager.py
│   ├── loop_guard.py, output_router.py, task_matcher.py, task_register(.json)
│   ├── prompts.py, capabilities.py, chains.py, step_runner.py, discovery.py
│   ├── memory.py, chat_persistence.py, results_store.py, lineage.py, provenance.py
│   ├── scheduler.py, cancel_signal.py, project_session.py, evidence.py, api_trace.py
│   ├── services/               script_isolation.py and its worker process
│   └── tools/                  276 tools, one module per domain, plus _helpers
├── services/              prompt refiner, tool router, response guard, task runner, learning
├── models/                confidence, sensitivity, egress gate, plan gate, model view, transactions, dataset status
├── validators/            schema contracts, P-code depth validation
├── representation/        map representation planner (profiler, planner, applier)
├── ui/                    dock, dialogs, chat formatting (Qt-free), icons, theme
├── logger.py, exceptions.py, net.py, proxy.py, release_notes.py
infrastructure/
├── auth.py                credentials: QGIS Auth Manager or session memory only
├── deps.py                optional-dependency checks
├── settings_keys.py       every QgsSettings key, namespaced cartogen_ai/
└── providers/             OpenRouter, Gemini, Ollama, Cartogen stub, OpenAI and Claude (not offered)
processing/                QGIS Processing provider (hub siting, service area)
```

## Why it is shaped this way

- **`cartogen_ai` is a PEP 420 namespace package** (no `__init__.py` in `src/cartogen_ai/`). The release zip's top folder is **`cartogen_ai_plugin`**, never `cartogen_ai`: a folder of that exact name in the plugins directory would be a regular package that shadows the namespace package and breaks every `cartogen_ai.core` import. `plugin_upload.py` refuses to build with that name. The name must also be a valid Python identifier, which plugins.qgis.org requires, so it contains no dots and does not start with a digit.
- **Entry points stay at the repo root** (`__init__.py`, `plugin_main.py`) because QGIS imports the plugin folder by name.
- **`agent_orchestrator.py` is the one big file** (about 2,000 lines). It was split once (dispatcher, usage tracker and history manager were extracted in the Phase 11 restructuring) and `_run_impl` has been kept below the lint complexity limit by moving logic into helpers.
- **What ships in the zip** is deliberately small: only `README.md`, `USER_GUIDE.md`, `TOOLS_REFERENCE.md`, the humanitarian catalogue and the screenshots from `docs/`; no tests, no `tools/`, no `site/`, no `service/`, no sample data, no binary documents, no hidden files. `tests/test_directory_validator.py` checks the built zip against the plugin directory's rules.

## Conventions you will see everywhere

- Every module that touches `qgis.core` has its own `QGIS_AVAILABLE` guard and degrades without it.
- Tool modules put **pure parsers and decision logic in separate functions** from the QGIS-touching code, so they are testable offline.
- Settings keys live only in `settings_keys.py`. Qt 6 scoped enums (`Qgis.MessageLevel.Critical`), imports through `qgis.PyQt`, never `PyQt5`/`PyQt6`.
- Frozen documents are never edited after the fact; see [Contributing](@development/contributing).
