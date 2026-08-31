# MultiTier Repository and Directory Architecture Specification

**Status:** Technical spec for the open-core split. Some parts are built and live in this repo
today (marked **Implemented** below); most of the private-repo side is **not built** — there is
no private repo yet. Written the same way `docs/OPEN_CORE_REPO_STRATEGY.md` and other roadmap
docs in this project are: an honest plan, not a claim of shipped capability. Where this doc and
`docs/OPEN_CORE_REPO_STRATEGY.md` overlap, this doc is the more detailed technical reference —
that doc stays the shorter business-rationale summary; the two should not be edited to disagree.

This spec transcribes, and then makes concrete against this actual codebase, the following
requirements as given:

> A two-repository model is used to isolate proprietary commercial enhancements from the
> open-source codebase. The Public Repository contains only the open-source foundational
> package, tests, and public documentation, released publicly under the chosen open-source
> license. The Private Repository houses proprietary extension plugins, license validation
> logic, enterprise modules, and secure release build pipelines. To ensure all software editions
> share the top-level import namespace without file conflicts, native Python namespace packages
> are used across the directories. The private repository stays updated with public repository
> changes via an automated one-way sync that pushes updates while protecting private commit
> history. Open-source editions are distributed via public PyPI or public GitHub Releases. Pro
> and Enterprise editions are distributed via gated website downloads as precompiled wheels or
> standalone executables (PyInstaller or Nuitka). Access tokens for repository syncing are stored
> securely using GitHub Secrets. Sensitive verification modules are stripped or properly compiled
> before distribution.

## 1. Repository split

| | Public repo (this one, `cartogen-ai`) | Private repo (not yet created) |
|---|---|---|
| Contents | Open-source Community package, tests, public docs | Pro/Enterprise modules, license validation logic, secure build pipelines |
| License | GPL v2 (see `LICENSE`) | Not yet decided — needs real legal review before any code or license-key mechanism ships (standing caveat, also raised in `docs/TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md` §3 and `docs/OPEN_CORE_REPO_STRATEGY.md`) |
| Import namespace it owns | `cartogen_ai.core` (and subpackages) | `cartogen_ai.pro`, `cartogen_ai.enterprise` (planned names, not yet built) |
| Relationship | Standalone, fully functional Community product on its own | Consumes the public repo as a one-way-synced upstream; not a fork |

**Implemented:** the public/private split as a *decision*, and the public repo's own contents,
are real. **Not implemented:** the private repo itself does not exist — nothing below describing
its contents is built.

## 2. Namespace package layout (Implemented)

PEP 420 implicit namespace packages — directories with **no** `__init__.py` at the point where
the shared namespace begins — let multiple, separately-installed distributions contribute
subpackages under one shared top-level import name with zero file conflicts. Concretely, in this
repo:

```
cartogen-ai/                       (public repo root)
├── src/
│   └── cartogen_ai/                ← NO __init__.py here (namespace root)
│       └── core/
│           ├── __init__.py         ← package proper starts here
│           ├── agent/              (45 files — full agent core, tool registry, providers)
│           └── ui/                 (6 files — dock widget, settings dialog, canvas highlight)
├── pyproject.toml                  → builds distribution "cartogen-ai-core",
│                                      package cartogen_ai.core (+ subpackages) only
├── __init__.py                     (QGIS plugin entry point, repo root — see §4)
└── plugin_main.py                  (QGIS plugin main class, repo root — see §3.1)
```

A hypothetical private repo would mirror the same pattern for its own distribution:

```
cartogen-ai-pro/                   (private repo, not yet created)
└── src/
    └── cartogen_ai/                ← also NO __init__.py (same namespace root)
        └── pro/
            ├── __init__.py
            └── ...                 (Cloud Connect Gateway client, RBAC/SSO, license validation)
```

When both distributions are `pip install`-ed into the same environment, Python merges
`src/cartogen_ai/` from each into one working `cartogen_ai` namespace — `cartogen_ai.core.*` and
`cartogen_ai.pro.*` resolve side by side, no file ever collides, and neither package needs to
know the other exists at import time. This is why `src/cartogen_ai/__init__.py` must **never** be
added in either repo — adding it would turn `cartogen_ai` into a regular package owned by
whichever distribution's copy wins on `sys.path`, breaking the merge for the other one.

`pyproject.toml`'s `[tool.setuptools.packages.find]` is scoped to
`include = ["cartogen_ai.core", "cartogen_ai.core.*"]` specifically so this repo's build only
ever claims `cartogen_ai.core` — never the bare `cartogen_ai` namespace itself.

## 3. Why the code moved out of the repo root (Implemented)

Before this restructure, `agent/` and `ui/` lived directly at the repo root, which is where
QGIS's plugin loader expects a plugin's importable code to start (see §4). That layout can't
coexist with a namespace package split, because `agent/`/`ui/` living at the root — rather than
under `src/cartogen_ai/core/` — gives the public repo no natural place for a private repo's
`cartogen_ai.pro`/`cartogen_ai.enterprise` to attach alongside it under a shared top-level name.
So the real code moved to `src/cartogen_ai/core/agent/` and `src/cartogen_ai/core/ui/`, and two
sys.path bootstraps (§4) were added so QGIS and the test suite can still find it.

The old root-level `agent/`/`ui/` directories and `cartogen_ai.py` (see §3.1) were moved out of
the repo root entirely — this sandbox's FUSE mount blocks `rm`/unlink of files created earlier in
the same session, but a same-filesystem `mv`/rename (which doesn't require a separate unlink of
the source the way copy-then-delete does) works fine; this was only discovered while diagnosing
§3.1's collision, after most of this session's earlier consolidation work had already settled for
the more conservative "overwrite with a MOVED stub, `.gitignore` it, `git rm --cached` it" pattern
because a straight `rm`/`mv`-to-elsewhere had been tried and failed at the time (moving *across*
filesystems, e.g. into a different mounted folder, still fails the same way — it silently falls
back to copy+delete, and the delete half fails). All three paths now simply don't exist at the
repo root at all: they were renamed into `_legacy_stubs/` (gitignored, excluded from the release
zip via `plugin_upload.py`'s `EXCLUDE_DIRS`), which is on the same filesystem as the rest of the
repo. `git add -A` picks these up as plain deletions, same as if they'd been removed by hand.

### 3.1 A second, sharper collision: the plugin's own main-class file

The repo root also used to hold `cartogen_ai.py`, the QGIS plugin's main class file, at the same
level as `__init__.py`. That name **directly collides** with the `cartogen_ai` namespace package
itself, not just with the moved `agent`/`ui` directories — and this one wasn't hypothetical: it
broke the test suite outright, twice, in two different ways:

1. First pass: renamed the class's *content* into a new file, `plugin_main.py`, and overwrote
   `cartogen_ai.py`'s content with a short "MOVED" stub docstring — the same pattern used for
   `agent`/`ui` moments earlier in this same session. Re-running the test suite still failed the
   same 31 tests, now with a *different* error: `ModuleNotFoundError: No module named
   'cartogen_ai.core'; 'cartogen_ai' is not a package`. The stub's *content* doesn't matter to
   Python's import resolution — a file merely *existing* at `cartogen_ai.py` is enough to bind the
   top-level name `cartogen_ai` to it as a regular (non-package) module, before the `src/
   cartogen_ai/` namespace directory is ever considered. A regular module or package anywhere on
   `sys.path` always wins over a namespace-package portion, regardless of `sys.path` order — so as
   long as repo root and `src/` were *both* on `sys.path` (true for the test suite and, per §4,
   QGIS itself), nothing short of the file's actual absence from that path was ever going to work.
2. Second pass, the actual fix: moved `cartogen_ai.py` out of the repo root entirely (see §3's
   `mv`-not-`rm` discovery), leaving only `plugin_main.py` there. `__init__.py`'s `classFactory()`
   now does `from .plugin_main import CartogenAi`. Re-ran the full suite after this: clean.

The general rule this leaves for future work: **no file or directory anywhere reachable from a
`sys.path` entry that also contains `src/cartogen_ai/` may itself be named `cartogen_ai`** — that
includes this public repo's own root and, symmetrically, the private repo's root once it exists.
A stub with that name is exactly as fatal as the original file — only its complete absence from
the path works.

## 4. QGIS loading path (Implemented, but unverified live)

QGIS's plugin loader is understood — not yet confirmed in a live QGIS session — to add a
plugin's own root directory to `sys.path` when it loads the plugin. `__init__.py` (repo root)
adds `src/` to `sys.path` before `classFactory()` triggers any import from `cartogen_ai.core.*`:

```python
_SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
```

`plugin_main.py` (repo root, the plugin's main class — see §3.1 for why it isn't named
`cartogen_ai.py`) then imports from the new location with absolute imports, e.g.
`from cartogen_ai.core.agent.agent import CartogenAi as AgentCore`.

**The sys.path bootstrap itself has not been tested in a real QGIS session.** Run
`docs/RELEASE_SMOKE_TEST.md` before the next release to confirm it actually resolves
`cartogen_ai.core.*` inside QGIS's own Python environment — don't take it on faith from the
reasoning above alone. (The §3.1 collision, by contrast, *has* been confirmed and fixed — that
one didn't need a live QGIS session to reproduce, since the same sys.path mechanics apply to the
plain Python interpreter running the test suite.)

`tests/__init__.py` does the equivalent for the test suite (verified every run, since the suite
simply wouldn't collect if this bootstrap were wrong — no separate live-verification gate needed
for this half).

## 5. One-way sync, public → private (Partially implemented — scaffold only)

- A GitHub Actions workflow in **this public repo**, `.github/workflows/sync-to-private.yml`,
  mirrors every push to `main` into a dedicated branch (`sync/public-core`) of the private repo.
- **Protecting private commit history** means: the workflow only ever pushes to that one
  dedicated branch, and only ever with a plain `git push` (no `--force`, no `+refs/...`
  force-push refspec). It never touches the private repo's own default branch or any branch
  containing the private repo's proprietary commits — those are exclusively the private repo's
  own history to manage (rebase, merge, or otherwise integrate the synced branch on its own
  schedule). The current scaffold already does this correctly (`git push private
  "HEAD:refs/heads/${PRIVATE_REPO_BRANCH}"` — no force flag); see `docs/IMPLEMENTATION_TRACKER.md`
  for the follow-up to add an explicit comment stating this is deliberate, not an oversight to
  "fix" later.
- Access token: `secrets.PRIVATE_REPO_DEPLOY_KEY`, a GitHub Secret scoped to this repo, holding an
  SSH deploy key scoped to only the private repo's `sync/public-core` branch (deploy keys are
  per-repo in GitHub, so this is naturally scoped — no separate PAT-permission audit needed once
  the key itself is provisioned correctly on the private repo's side).
- **Not implemented:** the workflow is disabled (`if: false`) because `PRIVATE_REPO` is still a
  placeholder (`REPLACE-ME/cartogen-ai-pro`) and the private repo doesn't exist. Nothing syncs
  today.

## 6. Distribution channels

| Edition | Channel | Format | Status |
|---|---|---|---|
| Community | Public PyPI (`cartogen-ai-core`) | Python wheel/sdist | **Not implemented** — `pyproject.toml` exists and defines the distribution, but there is no publish workflow (no `.github/workflows/publish-pypi.yml`) and nothing has ever been uploaded |
| Community | Public GitHub Releases | Plugin release zip (`plugin_upload.py` output) | **Implemented** — this is the existing, working release mechanism |
| Community | QGIS plugin repository | Plugin release zip | Planned, not yet submitted (see `docs/RELEASE_SMOKE_TEST.md`) |
| Pro/Enterprise | Gated website download | Precompiled wheel | **Not implemented** — no website gating, no build pipeline; depends on the private repo existing first |
| Pro/Enterprise | Gated website download | Standalone executable (PyInstaller or Nuitka) | **Not implemented** — tool choice between PyInstaller and Nuitka not yet made; that decision belongs to whoever builds the private repo's release pipeline, informed by real tradeoffs (Nuitka's better performance/harder-to-reverse-engineer output vs. PyInstaller's simpler, more battle-tested tooling) at the time |

Sensitive verification modules (license-check logic) must be stripped from source distribution or
compiled (e.g. via Nuitka, or `.pyc`-only distribution) before any Pro/Enterprise build leaves the
private repo's pipeline — a private-repo build-pipeline concern; nothing to strip or compile
exists yet since no license-validation code has been written anywhere.

## 7. What this doc does not decide

Same scope boundary as `docs/OPEN_CORE_REPO_STRATEGY.md` §"What this doc does not decide" —
license-key validation design (offline vs. online), pricing/commercial terms, and the private
repo's internal structure remain open, to be decided when Pro/Enterprise work actually starts.

## 8. Open follow-ups

1. Add a PyPI publish workflow for the Community package once there's a reason to (i.e. once
   someone other than the QGIS plugin zip actually consumes `cartogen-ai-core` from PyPI).
2. Create the private repo and fill in `sync-to-private.yml`'s `PRIVATE_REPO` placeholder.
3. Decide PyInstaller vs. Nuitka for Pro/Enterprise standalone executables when that pipeline is
   actually built.
4. Run `docs/RELEASE_SMOKE_TEST.md` in a live QGIS session to confirm the `src/`-relocation
   sys.path bootstrap in `__init__.py` (§4) actually works before the next release ships.
