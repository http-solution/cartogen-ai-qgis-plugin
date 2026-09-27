# Vector memory (LanceDB/Chroma) for `memory.py` — scoped, not recommended yet

**Status: scoping document, not a build plan.** Alaa asked to scope `LanceDB` or `Chroma` as
semantic retrieval on top of `core/agent/memory.py`'s spatial-memory system, following the same
method as the other three 2026-09-27 scoping docs (`RESTRICTEDPYTHON_SANDBOX_LAYER_SCOPE_2026-09-27.md`,
`PRESIDIO_EGRESS_SCAN_SCOPE_2026-09-27.md`, `SEMANTIC_ROUTER_TOOL_FILTER_SCOPE_2026-09-27.md`):
read what the system actually does first, install the real libraries, run them live against
realistic project data, report what actually happened.

**The short version: the premise needs correcting before the technology question matters.** The
original pitch was "real semantic retrieval over past decisions/notes... erasure becomes delete by
id." But `get_formatted_memory_context()` does **no retrieval at all today** — it dumps every
stored note into the prompt unconditionally, every turn. There is nothing to make "more semantic"
because nothing is currently being searched. The live testing here confirms both libraries *can*
do the job well (Chroma's bundled embedding model in particular gave excellent results), but
adopting either is solving a scaling problem this project has not yet observed, not fixing a
retrieval-quality problem that exists today.

## 1. What `memory.py` actually does (this reframes the whole question)

`SpatialMemoryManager` stores three kinds of state: per-project notes (`store_project_note`,
opt-in persistence — GDPR finding F6), global notes (`store_global_note`, one JSON blob under a
single `QgsSettings` key, unbounded, `clear_global_notes()`/`delete_global_note()` — GDPR finding
F1), and a capped 50-entry action log. Global notes use key prefixes (`pref:`, `rule:`, `usage:`,
everything else) written by `core/services/learning.py`'s auto-inference from tool usage and
user corrections.

**`get_formatted_memory_context()` is the function that would call a retrieval step, and it
doesn't have one.** It dumps every project note, every global note bucketed by prefix, and the
last 5 actions into a markdown block, unconditionally, injected into the system prompt on every
turn. The *only* slicing anywhere in this pipeline is `usage:` counts sorted and cut to the top 5
— unrelated to query relevance, just "what's been used most." `pref:`, `rule:`, and other notes
are included in full, with no cap, every turn, regardless of whether the current query has
anything to do with them.

This means a vector database's actual selling point — "retrieve only what's relevant to this
query" — isn't competing against a worse retrieval mechanism here. It's competing against *no*
mechanism. Adopting one would be a genuinely new capability (bounded, relevant context instead of
an ever-growing unconditional dump), not a quality upgrade to an existing search.

## 2. Is there an actual problem today?

Grepped `docs/IMPLEMENTATION_TRACKER.md` and `docs/BUG_TRACKER.md` for `memory.*token`,
`vector.*memory`, `LanceDB`, `Chroma` — **zero hits.** No live bug report, no user complaint about
memory context size, no measured token-budget issue has ever been recorded for this system,
unlike Presidio (which had a prior G4 rejection to check against) or semantic-router (which had a
named bug, BUG-2026-09-13-1). This is genuinely greenfield.

`learning.py` has no cap on the total number of `pref:`/`rule:` notes it will accumulate — only
`usage:` gets sliced, and only at format time. Over a long-lived global QGIS profile (global notes
are QGIS-installation-wide, not per-project) this is a plausible, real, but **not-yet-observed**
growth path: nothing currently measures or bounds it. Stated honestly: this is a risk worth
watching, not a fire.

## 3. What was actually tested

Both libraries installed in a clean virtualenv (`/tmp/vecdb_venv`): `lancedb` v0.39.0, `chromadb`
v1.5.9. A synthetic-but-realistic set of 9 memory notes was built matching this project's actual
key-prefix conventions (`pref:crs`, `rule:buffer_units`, `rule:sensitivity_default`,
`other:known_issue`, etc.) and 4 realistic new-turn queries against them, run through: (a) top-K
semantic retrieval, (b) reopen-in-a-fresh-process persistence, (c) delete-by-id (matching
`delete_global_note()`), (d) full-collection wipe (matching `clear_global_notes()`/
`clear_project_notes()`).

**Embedding backend note, same constraint as the semantic-router test:** this sandbox blocks
`huggingface.co` outright. LanceDB ships no bundled embedding function — it is a pure
vector-store, bring-your-own-vectors library — so its query test reused the same spaCy
`en_core_web_md` static-vector substitute from the semantic-router doc. **Chroma is different: it
ships a default local embedding function (`all-MiniLM-L6-v2` via `onnxruntime`) that downloads
its weights from `chroma-onnx-models.s3.amazonaws.com`, not Hugging Face Hub — and that host is
NOT blocked here.** This let Chroma's *actual default, zero-configuration* embedding be tested
for real, not substituted.

### 3a. Retrieval quality — LanceDB with the spaCy substitute (weak embeddings, same as semantic-router's test)

| Query | Expected top-1 | Actual top-1 |
|---|---|---|
| "what CRS does this user like to work in" | `pref:crs` | wrong (`rule:gdacs_scope`) — `pref:crs` ranked 2nd |
| "how should I interpret a buffer distance the user didn't give units for" | `rule:buffer_units` | wrong (`rule:gdacs_scope`) — correct note ranked 2nd |
| "is there anything sensitive about layers loaded from local files" | `rule:sensitivity_default` | correct |
| "what's slow about the UNHCR data source" | `other:known_issue` | wrong (`rule:sensitivity_default`) — correct note ranked 2nd |

Only 1 of 4 exact top-1 hits (the other 3 had the right note ranked 2nd, still usable, just not
best). **Same weak-embedding pattern as the semantic-router test** — this is a property of the
spaCy GloVe-style vectors, not of LanceDB, but it's the only backend actually testable for LanceDB
in this sandbox, since it bundles no embedding of its own.

### 3b. Retrieval quality — Chroma with its own real default embedding (MiniLM, downloaded successfully)

| Query | Expected top-1 | Actual top-1 |
|---|---|---|
| "what CRS does this user like to work in" | `pref:crs` | **correct** |
| "how should I interpret a buffer distance the user didn't give units for" | `rule:buffer_units` | **correct** |
| "is there anything sensitive about layers loaded from local files" | `rule:sensitivity_default` | **correct** |
| "what's slow about the UNHCR data source" | `other:known_issue` | **correct** |

4 of 4, cleanly separated distances (0.5–1.6 for correct hits vs. 1.5+ for the nearest wrong one).
Run with Chroma's *own* embedding function on Chroma with the spaCy substitute (for an
apples-to-apples library comparison) reproduced LanceDB's exact same 1-of-4 result — confirming
the retrieval-quality difference in the table above is about the embedding backend, not the
vector-store engine. **The real, practical finding is that Chroma's bundled default happens to
work in this specific sandbox where the recommended backends for both LanceDB (BYO, no default)
and semantic-router (`FastEmbedEncoder`/`HuggingFaceEncoder`, blocked) do not** — a genuine,
if environment-specific, ergonomic edge.

### 3c. Persistence, delete-by-id, full wipe — both libraries, both pass

| Behavior | LanceDB | Chroma |
|---|---|---|
| Reopen table/collection in a fresh client object, data survives | 9/9 rows | 9/9 rows |
| Delete by id (`delete_global_note()` equivalent) | works, count -1, gone from results | works, count -1, gone from `.get()` |
| Full wipe (`clear_global_notes()` equivalent) | `drop_table` leaves zero tables | `delete_collection` leaves zero collections |

Both map cleanly onto this project's existing GDPR-driven erasure semantics (F1/F6) — no gap
found on either side.

### 3d. Dependency weight — a real, measured difference

| | LanceDB | Chroma |
|---|---|---|
| Installed package tree | lean: `numpy`, `pyarrow`, `lance-namespace` | heavy: pulled in `onnxruntime` (67MB), `kubernetes`, `opentelemetry-*` (6 packages), `huggingface-hub`, `tokenizers`, `grpcio`, and ~35 more transitive packages |
| `pip install` transitive package count added | ~5 | ~45 |
| Bundled embedding model | none (BYO vectors) | `all-MiniLM-L6-v2` ONNX, ~79MB download on first use |

This is the real tradeoff the doc's evidence surfaces: Chroma's batteries-included default is what
made §3b's clean 4/4 result possible with zero extra engineering, but it comes with a
`kubernetes`-client-sized dependency tree for a QGIS desktop plugin that currently has none of
this. LanceDB's dependency footprint is far closer to what a plugin install should look like, at
the cost of needing a real embedding-backend decision of its own (same open question the
semantic-router doc left for `OllamaEncoder`).

## 4. What this confirms and what it doesn't

- **Confirmed:** both libraries work correctly on the mechanics this project's memory system
  actually needs — real on-disk persistence, delete-by-id, full-collection wipe, all matching
  `memory.py`'s existing GDPR-driven erasure contract with no rework needed there.
- **Confirmed:** semantic retrieval quality is good when given a real embedding model (Chroma's
  bundled MiniLM, §3b) and mediocre with the same weak spaCy substitute both the LanceDB test here
  and the semantic-router test used (§3a) — this is consistently an embedding-backend property
  across all three scoping docs that touched retrieval, not a vector-store-engine property.
- **Not confirmed, and this is the load-bearing finding:** that this project has an actual problem
  today that retrieval would fix. `get_formatted_memory_context()` doing an unconditional full
  dump (§1) is a real structural fact; whether it has caused or will cause a real token-budget or
  relevance problem is not measured or reported anywhere in this project's own trackers (§2).

## 5. Recommendation

**Not now, and not framed as "add semantic search" if it is ever revisited.** Three reasons:

1. **No evidence of the problem it would solve.** Unlike RestrictedPython (real bypass reports
   existed) or semantic-router (a real named bug), there is no live report of memory context being
   too large, too irrelevant, or costing meaningful tokens. Building retrieval infrastructure
   ahead of a demonstrated need is exactly the kind of speculative abstraction this repo's own
   engineering conventions (`CLAUDE.md`) caution against.
2. **If the real problem shows up, it may have a much cheaper fix first.** An unbounded `pref:`/
   `rule:` note count (§2) could be addressed with a simple cap or a time/relevance-agnostic
   trim — the same shape of fix `usage:` notes already get (top-5 by count) — before reaching for
   a new embedding + vector-store dependency. That's a smaller, more reversible change worth
   trying first if and when growth is actually observed.
3. **The dependency-weight tradeoff (§3d) is a real product decision, not an engineering call** —
   Chroma's batteries-included ergonomics (the only backend that gave clean 4/4 retrieval in this
   sandbox with zero extra work) come with a `kubernetes`/`opentelemetry` dependency tree that is a
   meaningful shift for a QGIS desktop plugin; LanceDB's lean footprint avoids that but reopens the
   same unresolved embedding-backend question the semantic-router doc left open
   (`OllamaEncoder`, untested here for lack of a local server, same as that doc). Per this repo's
   own `CLAUDE.md` ("flag it with a clear recommendation instead of applying it silently"), this
   tradeoff is logged in `docs/IMPLEMENTATION_TRACKER.md` §1.13 rather than decided here.

If this is ever revisited, start from "do we have a measured token-budget or relevance problem,"
not from "which vector database" — the technology choice is the easy part; both libraries tested
clean.

Not built. `lancedb`, `chromadb`, `spacy`, and `en_core_web_md` were removed from this environment
after testing; none of this is a new dependency of this repo.

## 6. What was and wasn't verified

- Verified live: both libraries' actual insert/query/persist/delete/wipe behavior in embedded
  (no-server) mode, against synthetic-but-realistic notes matching this project's real key-prefix
  conventions, and against 4 realistic new-turn queries — not toy examples, not taken from either
  library's own documentation.
- Verified live: Chroma's default embedding function actually works in this specific sandbox
  (downloads from an S3 host the network policy doesn't block), unlike the transformer-based
  encoders the semantic-router doc could not test. Not assumed to hold on every deployment's
  network policy — flagged as sandbox-specific, same caveat pattern as the other docs' network
  findings.
- Not verified: LanceDB against a real (non-spaCy-substitute) embedding backend — same gap the
  semantic-router doc left for `OllamaEncoder`, and for the same reason (no local Ollama server in
  this sandbox). Not assumed to perform identically to Chroma's MiniLM result; a real prototype
  would need to test this directly.
- Not verified: performance/latency at realistic note-count scale (hundreds to thousands of
  notes) — the 9-note test set here is representative of *content shape*, not of the scale a
  years-long global profile might eventually reach. Not measured because §2 found no evidence such
  scale has been reached yet.
- Not measured: actual token counts saved by switching from full-dump to top-K retrieval on real
  memory contents — no real (non-synthetic) memory store was available to measure against in this
  sandbox.
