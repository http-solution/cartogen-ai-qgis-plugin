# `tool_router.py`'s top-40 filter — semantic-router prototype, not a build plan

**Status: scoping document, not a build plan.** Alaa asked to scope `semantic-router`
(aurelio-labs) as a replacement for `core/services/tool_router.py`'s keyword-scoring top-40
candidate filter. Same method as the other two 2026-09-27 scoping docs
(`RESTRICTEDPYTHON_SANDBOX_LAYER_SCOPE_2026-09-27.md`, `PRESIDIO_EGRESS_SCAN_SCOPE_2026-09-27.md`):
install the real library, run it against this project's own real tools and real known failure
cases, report what actually happened.

**The short version: semantic similarity genuinely works here, but not for free.** With zero
extra authoring effort — the realistic "just point it at the tools we already have" deployment —
it performs *worse* than the current keyword scorer on the exact cases it was proposed to fix.
With authored example phrasings per tool (comparable effort to what `_TOOL_ALIASES` already
costs), it works well and generalizes to paraphrases the current system cannot match at all. This
is a genuine prototype-worthy result, not a "yes" or a "no" — see §5.

## 1. What `tool_router.py` actually does (narrows the comparison)

`filter_relevant_tools(user_query, top_k=40)` is a **candidate-set filter**, not final tool
selection: word-boundary keyword matching against each tool's name and description (name-word
match: +10, description-word match: +2/word), plus a hand-curated `_TOOL_ALIASES` dict (e.g.
`"rank the districts"` → `calculate_severity_index`) for exactly the paraphrase gap keyword
matching cannot close on its own. Returns up to 40 of the 178 registered tool schemas to the LLM,
which then picks the actual tool to call. `semantic-router`'s own primary API
(`SemanticRouter.__call__`) returns a single best route by default — matching the comparison
requires its `limit=N` parameter, confirmed to exist and to work (§3).

`_TOOL_ALIASES` exists because of a real, live-documented failure (BUG-2026-09-13-1, this
project's own tracker): a query sharing no vocabulary with the target tool's name/description
scored zero and never made the candidate set. That's exactly the shape of problem semantic
similarity is supposed to solve, and exactly the test case used here.

## 2. What was actually tested

`semantic-router` v0.1.16 (current on PyPI), installed in a clean virtualenv.

**Encoder used: a real, custom `DenseEncoder` wrapping spaCy's `en_core_web_md` static word
vectors**, not the transformer-based embeddings (`FastEmbedEncoder`/`HuggingFaceEncoder`)
semantic-router's own examples recommend. Those need a Hugging Face Hub model download at first
use, and **this sandbox's network policy blocks huggingface.co and its mirrors outright**
(confirmed live: `httpx.ProxyError: 403 Forbidden`) — a real deployment on a normal machine would
not hit this, but it could not be tested here. spaCy's model downloads from `github.com` releases,
which is reachable, so this is a real embedding space, just an older GloVe-style one rather than a
modern sentence-transformer. Flagged explicitly, not glossed over — see §6.

**Test 1 — zero extra authoring, the tool's own registered description as the sole "utterance"
per route, against all 178 real tools** (`docs/TOOLS_REFERENCE.md`'s actual content, not a toy
subset) — the realistic "just point semantic-router at what we already have" deployment:

| Query (real `_TOOL_ALIASES` case) | Expected tool | Result (out of 178, top 40 checked) |
|---|---|---|
| "rank the districts" | `calculate_severity_index` | **NOT in top 40** |
| "who's helping in the worst-hit areas" | `calculate_presence_gap` | rank 2/40 |
| "who else is working in this district" | `load_3w_data` | **NOT in top 40** |
| "is it getting worse here" | `analyze_incident_trend` | **NOT in top 40** |
| "make something to send to donors" | `generate_html_dashboard` | **NOT in top 40** |
| "buffer this layer by 500 meters" *(easy case, control)* | `buffer_analysis` | rank 4/40 |
| "export this layer to CSV" *(easy case, control)* | `export_to_csv` | rank 1/40 |

**4 of 5 of the exact cases `_TOOL_ALIASES` exists to fix are not even in the top 40 out of 178**
with zero-authoring semantic-router — worse than today, where the alias entries make all 5 score
positively. The two easy control cases (already handled fine by keyword matching) still rank
well, so this isn't a wholesale regression — but it does not deliver the improvement it was
proposed for, as deployed with no extra work.

**Test 2 — the same 5 hard cases, with ~4-5 short authored example phrasings per route** (a small
subset of routes, not all 178 — see §5 for what full coverage would cost) instead of the bare
description:

All 5 correct, including "rank the districts" and the other 4 that failed outright in Test 1.

**Test 3 — genuinely novel paraphrases, not present verbatim in `_TOOL_ALIASES` or in Test 2's
authored utterances** (checking the actual claimed benefit: generalizing beyond exact phrases
someone thought to write down, which literal alias matching structurally cannot do):

| Novel query | Expected | Result |
|---|---|---|
| "which of these zones is in the worst shape" | `calculate_severity_index` | correct |
| "show me which villages have nobody responding to them" | `calculate_presence_gap` | **wrong** (got `generate_html_dashboard`) |
| "has security been deteriorating recently" | `analyze_incident_trend` | correct |
| "I want a shareable interactive map for the funding committee" | `generate_html_dashboard` | correct |

3 of 4 — real generalization, not perfect. This is the one thing keyword/alias matching cannot do
at all (none of these words appear in the relevant tool's name, description, or existing alias
list), and it's the actual case for semantic similarity as a technique.

**Latency and build cost:** embedding all 178 real tool descriptions took ~3.6s once (a one-time
cost at startup/cache-build, not per query); each routed query after that took ~4-5ms. Not a
performance concern either way.

## 3. Structural fit, confirmed

`SemanticRouter.__call__(text, limit=N)` returns a ranked list of `N` best-matching routes, not
only the single best — confirmed by direct inspection of the method signature and by Test 1 above
(`limit=40`, checking rank). The earlier framing of this as a single-choice classifier (a real
concern before checking) does not hold for `semantic-router` specifically; it can do the
candidate-filtering job `tool_router.py` actually needs.

## 4. What this confirms and what it changes about the original framing

The original recommendation ("no fine-tuning required... more natural match") undersold the real
cost. **Semantic similarity does not remove the "someone must anticipate real phrasings per tool"
work `_TOOL_ALIASES` already pays — it moves it from short alias words to short example sentences,
at comparable effort per tool** (Test 2's 4-5 phrasings per route is the same order of magnitude
as `_TOOL_ALIASES`' existing per-tool entries). Skip that work and use only what's already
registered (Test 1), and the result is worse than today on the exact cases motivating the
proposal, not better. The real, demonstrated benefit is narrower and more specific than "better
routing generally": genuine generalization to paraphrases nobody explicitly wrote down (Test 3),
which `_TOOL_ALIASES`' literal substring matching cannot do at all, at any authoring effort.

## 5. Recommendation

**Prototype further before committing — not a "yes," not a "no," with a concrete scope for what
the prototype needs**, unlike Presidio's flat rejection: the technique demonstrably works when
given real input, the question is whether the authoring cost is worth it project-wide.

If pursued, the prototype should specifically NOT be "swap the encoder in and use existing
descriptions" (Test 1's result is the reason not to ship that). It needs:

1. **Authored utterances for all 178 tools**, not a 5-tool subset — a real one-time writing
   project comparable in scope to (likely larger than) `_TOOL_ALIASES`' current ~15-20 entries,
   since every tool would need coverage, not just the ones that have already hit a live bug
   report. Not sized here — this is real, separate work.
2. **A real embedding backend decision**, not the spaCy substitute used for this scoping pass.
   `OllamaEncoder` is the most natural fit for this specific project — Ollama is already a
   first-class configured local provider here (`infrastructure/providers/ollama.py`), unlike
   FastEmbed/HuggingFace, which need a Hub download this sandbox couldn't even test. Untested
   here (no local Ollama server in this sandbox) — a real prototype needs to verify it against an
   actual running Ollama instance with an embedding-capable model (e.g. `nomic-embed-text`).
3. **A measured A/B against real query logs**, not five hand-picked hard cases — this document's
   evidence is real but deliberately adversarial (chosen because they're the known failure
   class); a fair prototype needs the easy-case regression risk checked at scale too, not just
   the two control cases here.
4. **A decision on hybrid vs. replacement**: keeping `_TOOL_ALIASES`' exact-match speed for the
   cases it already covers, adding semantic similarity only for what it still misses, is a real
   design option this document does not choose between — not sized here.

Not built. `semantic-router`, `spacy`, and `en_core_web_md` were removed from this environment
after testing — none of this is a new dependency of this repo.

## 6. What was and wasn't verified

- Verified live: `semantic-router` v0.1.16's actual routing/ranking behavior against all 178 of
  this project's real registered tool descriptions and real known-hard query cases from this
  project's own bug history, using a genuinely working (if non-default) embedding backend.
- Not verified: the transformer-based encoders (`FastEmbedEncoder`, `HuggingFaceEncoder`)
  semantic-router's own documentation recommends — blocked by this sandbox's network policy
  (Hugging Face Hub unreachable). Not assumed to perform identically to the spaCy substitute used
  here; a real prototype needs to test one of these directly.
- Not verified: `OllamaEncoder` against a real local Ollama server — no server available in this
  sandbox. Named above as the most promising direction for a real prototype specifically because
  this project already ships Ollama integration.
