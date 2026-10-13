---
description: The offline test suite, the live QGIS job, lint, type and packaging checks, and what each can and cannot prove.
---
## Running the tests locally

```bash
# Full unit suite; no QGIS installation needed.
# -t . matters: without it discover() treats tests/ as its own top level and never runs
# tests/__init__.py's src/-on-sys.path bootstrap, so every cartogen_ai.core import fails.
python -m unittest discover -s tests -t . -p "test_*.py" -v

python -m pip install ruff==0.17.0 && ruff check .     # must stay at zero violations
python -m pip install mypy types-requests && mypy
python plugin_upload.py                                 # builds the release zip
```

The suite is **{{tests}} test functions in {{test_files}} files**. Tests that need QGIS or optional libraries are skipped in the offline run; the QGIS ones run in CI.

## What CI runs

Workflow `.github/workflows/tests.yml`, on every push to `main` and every pull request.

| Job | What it proves |
|---|---|
| **secret-scan** | `gitleaks` over the pushed range finds no keys or tokens. |
| **test** (Ubuntu with Python 3.10 and 3.11, Windows with 3.11) | The offline suite passes on the declared Python floor and on Windows, where real path-handling bugs have been caught. Also: byte-compile, `ruff check .` (pinned version), `mypy`, and the release-zip packaging check (the zip is built, has the right top folder, and passes the directory validator). |
| **qgis-live-tests** (QGIS 4.2.2 official image, pinned by digest; a PostGIS 16 service) | Real `QgsApplication` and real Qt widgets: `tests/test_*_live.py` ({{live_files}} modules) run via `tests/_ci_run_live_tests.py`, which force-collects and pumps the Qt event loop before `exitQgis()` so a known interpreter-shutdown segfault does not mask results. Includes the read-only SQL tool against a real database, the plugin load → unload → reload smoke test, and the raster, chunking, network and widget tests. |
| **CodeQL** | Static analysis of Python, JavaScript/TypeScript and workflow files. |

A control process with no plugin code is run first, so a shutdown crash that also occurs without the plugin is recognised as environmental, not a regression.

## Conventions

- **Offline first.** Pure logic is kept free of Qt and QGIS so the plain job can test it (chat formatting, tool routing, colours, task matching, the loop guard, the output router).
- **A live test for anything that touches QGIS objects.** Say in the commit and release notes whether a change was live-tested, CI-only or hand-tested.
- **Structural tests for footguns the interpreter will not warn about.** A duplicate dict key once silently discarded tool-router aliases; an `ast`-based test now guards it. Other examples: every tool classified by operation type; every tool in the capability table exists; every registered function accepts the arguments its schema advertises; every network-calling tool is declared network-only or two-phase; every feature reader is counted by the egress-gate coverage scan.
- **Mutation-check important tests.** Re-introduce the bug and confirm the test fails; the registry-signature test was verified this way.

## What the tests cannot prove

CI cannot prove that a real model chooses the right tool, that a plan is sensible, that the dock looks right on a user's desktop, or that Stop is heard during a long real analysis. Those need a person in desktop QGIS: see [Live testing in QGIS](@development/live-testing). A green CI is stated in each release as "CI-checked, not hand-tested" until a hand test says otherwise.
