# Repo Strategy: Public Core + Private Pro/Enterprise

**Status:** Decided direction for how code is organized across editions — **not yet built**.
This repo (`cartogen-ai`, public, Community edition) exists and is real. The private
Pro/Enterprise repo described below does not exist yet; nothing in this document is
implemented. Written the same way `docs/TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md` and other
roadmap specs in this project are — as an honest plan, not a claim of shipped capability.

## The decision

Two repositories, not one:

1. **This repo (public)** — the Community edition. Open source, GPL v2 (see `LICENSE`), the
   full 131-tool registry, no license key, no gating. Anyone can clone it, read it, and run it
   standalone. This is the actual product most users will ever touch.
2. **A private repo (not yet created)** — Pro/Enterprise-only modules: the hosted Cloud Connect
   Gateway client, RBAC/SSO integration, M365/SharePoint/Power BI push, and any other
   capability described in `docs/PRODUCT_TIERS.md` §2–3 that depends on backend infrastructure
   or is deliberately not given away for free. This repo is **not** a fork of the public one —
   it *builds on* the public core (see sync mechanism below) and adds proprietary code on top.

This resolves a tension `docs/TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md` §3 flagged and
explicitly did not settle: that proposal's "Community tier, source locked" framing conflicted
with this project's actual GPL v2 license. Under this two-repo model, Community stays genuinely
open in the public repo — nothing about the free tier's source becomes locked. Only the
*additional* Pro/Enterprise code, which doesn't exist in the Community product at all, lives
under separate (proprietary) terms in the private repo. `docs/TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md`
§3's licensing-decision flag is now resolved by this doc for the *Community* side; it's still an
open question exactly what license governs the private repo's own code, which isn't this
project's GPL v2 and should be decided with real legal counsel before that repo is monetized —
same caveat that proposal already raised, not repeated lightly here.

## Sync mechanism: one-way, public → private

The private repo is not hand-maintained as a separate copy (this project already learned that
lesson once — see `CHANGELOG.md`'s `[1.4.0]` entry on why the old `build_cartogen_ai.py`
dual-tree setup existed and why it was retired). Instead:

- A GitHub Actions workflow in **this public repo** runs on every push to `main` and mirrors the
  commit into a dedicated branch (e.g. `sync/public-core`) of the private repo, using a deploy
  key or fine-grained PAT scoped only to that one branch of the private repo.
- The private repo treats that branch as a vendored upstream — merging or rebasing its own
  Pro/Enterprise-only commits on top of it, the same way any project consumes an upstream
  dependency it doesn't want to fork. Exactly how the private repo integrates it (subtree merge,
  a periodic rebase, or something else) is that repo's own decision to make once it exists; this
  doc only commits to the public side staying a clean, honest, standalone Community product with
  a one-way export point.
- **One-way only.** Nothing flows from the private repo back into this one automatically — Pro/
  Enterprise code never leaks into the public repo by construction, not by discipline alone.

See `.github/workflows/sync-to-private.yml` for the (currently inactive) workflow scaffold —
it needs a real target repo URL and a deploy-key secret before it can run.

## Distribution

- **Community** — same as today: a release zip built by `plugin_upload.py` from this repo,
  installable via `Plugins → Install from ZIP` in QGIS, or eventually the public QGIS plugin
  repository. No account, no key.
- **Pro/Enterprise** — built from the private repo, distributed as a downloadable installer/zip
  from the project website, gated by license-key validation. The validation mechanism itself
  (what a license key is checked against, offline vs. online validation, what happens on
  expiry) is not designed yet — it depends on the still-unbuilt Cloud Connect Gateway backend
  described in `docs/PRODUCT_TIERS.md` §2, since license validation and the gateway's own
  per-user auth are likely the same underlying system, not two separate things to build.

## What this doc does not decide

- The private repo's own internal structure, license terms, or hosting details.
- Whether license-key validation happens client-side (offline, crackable) or against a hosted
  service (online, requires the gateway backend to exist first) — a real design tradeoff for
  whenever Pro/Enterprise work actually starts.
- Pricing, billing, or the commercial terms in `docs/PRODUCT_TIERS.md` §2–3 — this doc is about
  where code lives and how it moves, not the business model itself.

## Next steps (not done, no timeline implied)

1. Create the private repo when Pro/Enterprise work actually begins — not before, since there's
   nothing to put in it yet.
2. Fill in `.github/workflows/sync-to-private.yml`'s placeholders once that repo exists.
3. Decide the private repo's license and get real legal review before any Pro/Enterprise code
   or license-key mechanism ships — same standing caveat as
   `docs/TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md`.
