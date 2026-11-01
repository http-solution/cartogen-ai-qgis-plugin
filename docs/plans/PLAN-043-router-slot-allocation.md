# PLAN-043: How the router fills its 28 slots (proposal, not built)

Status: in progress

## Goal
A long request with several steps ("count the clinics per district, colour the districts by the count, put it on a printable map") is offered a tool for EVERY step, not only for the step that happens to score highest. Today that depends on which tools win ties, and on phrases patched one wording at a time (PLAN-042 rounds 1 to 5: 271 requests, 60 misses fixed). This plan proposes changing how slots are filled so the misses stop appearing, and says how to prove it before and after.

## Measured today (2026-11-01, real router, 240 test requests: 116 data rows, the GOLDEN and GOLDEN_LONG tables)
1. **Slots are not short for what we test.** The worst-ranked needed tool sits at position 11 or better for 200 of 240 requests, 12 to 19 for 34, and 20 to 27 for 6. No request needs more than 28. But this is after five rounds of phrase patches, so it shows the patches work, not that the design is sound.
2. **The cut is decided by ties.** After the nine always-on tools and `find_tools`, about 18 slots remain. In 178 of 240 requests the tools at the cut (19th and 20th scored) have the SAME score, and the order inside a tie is alphabetical by tool name (kept deliberately for prompt caching, see the comment in `tool_router.py`). So a tool survives or drops because of its name.
3. **Crowding in long requests.** Before round 5, 13 of 25 long multi-step requests were missing at least one needed tool. Cause, shown on "hospitals per district on a printable map": three tools matched the first clause at 100 points, the print layout scored 4 (under the long-request floor of 6) and was dropped. One added phrase pushed a neighbouring tool out of the 28 in the same round.
4. **Median 48 tools score above the floor** for a request, against about 18 free slots, so most requests are cut somewhere. Average tool schema is about 260 tokens, so each extra slot costs about 260 tokens per model call.
5. **Not measured, and the big caveat:** I wrote all 240 requests myself, so they share my wording; real users differ. No model was run, so "offered" is not "chosen".

## Options
| Option | What it does | Cost | Risk |
|---|---|---|---|
| A. Keep as is | Continue patching phrases when a miss is found | none | misses keep appearing in long requests; each patch can displace a neighbour |
| B. Better tie-break | Replace alphabetical order inside a tie with a stable, meaningful second key (for example number of distinct query words matched, then tool specificity), still deterministic so the tool list stays cache-friendly | small | changes which tools are offered for many requests; needs the full replay |
| C. Per-step slots | Split the request into steps (sentences, "then", "and", commas), score each step on its own, and give each step a share of the free slots (for example round-robin from each step's ranking), then fill the rest by overall score | medium | a bad split gives a step too many or too few slots; needs tests on punctuation, Arabic and French |
| D. Larger k for long requests | Raise k for requests over 25 words (28 to 40) using the existing setting | tiny code, about +3,100 tokens per call on long requests only | hides the ordering problem instead of fixing it; costs money on every long request |
| E. Embeddings | Semantic match | new dependency or network call | rejected before: offline plugin, hard to test deterministically |

## Recommendation
**B and C together, with D off by default.** C attacks the measured cause (one strong step crowds out the others); B removes the arbitrary alphabetical decisions at the cut; D stays a setting the owner can raise if a hand test shows misses. Keep the tool list order deterministic. Do not change the nine always-on tools or `find_tools`.

## Scope
In (if the owner approves): a step splitter and per-step slot allocation in `core/services/tool_router.py`; a tie-break key; a replay harness that reports, per request, which needed tools are offered, the slot count and the tokens; tests.
Out: embeddings; changing phrases; changing `top_k` defaults; any model-in-the-loop evaluation (see Acceptance 4).

## Acceptance
1. **Held-out set first.** Before any code, collect at least 40 NEW long requests that were never used to patch a phrase: the owner's real chat prompts (the transcripts from the hand tests, the 385 plain prompts in `docs/HAND_TEST_rc46_algorithms_plain.csv` joined into multi-step requests) and 20 I write blind. Record the baseline: how many are missing a needed tool today.
2. **Better on the held-out set** (fewer requests missing a tool) and **no regression** on the 240 existing requests, with the same median tokens per call for short requests (k stays 28) and at most +10 percent for long requests.
3. **Deterministic:** the same request gives the same tool list in the same order on every run (prompt caching).
4. **Not claimed:** that a model chooses the right tool. That needs a hand test with a real model (ledger hand row to be added with the work).

## Guard tests
To be written with the work: a replay test over the held-out file with a required improvement threshold; a determinism test; step-splitter unit tests (commas inside numbers, "and" inside a place name, Arabic and French connectors); the existing `tests/test_routing_requests_data.py`, `tests/test_tool_router_basics.py` and the alias-owner replay stay as they are.

## Rollback
The new allocation sits behind one function; keep the old path selectable by a setting (`tool_router_allocation = classic`) for one release, then remove it.

## Decisions needed from the owner
1. Approve B and C, or choose A (keep patching) or D (bigger k for long requests only)?
2. Provide or point to 40 real long prompts for the held-out set (chat exports are enough; metadata only is not, the request text is what is measured).

## Status log
- 2026-11-01: written after PLAN-042 round 5, from the measurements above. No code. Master list row RT-1 (Decision needed).
- 2026-11-01 (later): real evidence for the tie-break problem. The owner's per-call log of the Taiz run shows eight never-used tools carried on every call because they tied at score 8 and sorted first alphabetically (about 17 percent of the run's tokens). A first, cheap response is in PLAN-042's log: the long-request floor moved from 6 to 9. That leaves the question of the tie-break order and per-step slots open, and this plan still needs the owner's choice.

- 2026-11-01 (owner said go; B and C chosen as recommended): held-out set 1 written FIRST (41 long multi-step requests, wording not taken from any phrase). Baseline: 24 of 41 requests miss at least one needed tool (33 tools). Built B (tie-break by shared words) and C (per-step slots, each step guaranteed its best two tools, behind a setting) and replayed: 24 of 41 both ways, same 33 missing tools, +0.3 percent tool tokens, deterministic. Diagnosis of the 33 misses: 32 never scored above the long-request floor of 9 on ANY step (a vocabulary gap: "colour the districts from few to many" never reaches apply_graduated_style, "total population of each district" never reaches zonal_statistics); 1 scored 10 but was cut. So the plan's premise (a shortage of slots) is not what the data shows, and by its own acceptance 2 (better on the held-out set) B and C do not qualify: they were removed, not shipped. Also tried: weighting description words by rarity (IDF) at five settings: 24 to 22 misses at best, with +30 percent tokens and a regression on the existing 156 rows: rejected.
- 2026-11-01 (same day): patched the vocabulary gaps of set 1 (about 120 phrases beside 23 tools, plus Arabic and French phrases for three tools): set 1 24 to 2 misses, existing 156 rows 0 misses, tokens on the existing rows 5,071 to 5,073, on set 1 5,353 to 5,802 (+8 percent). Then wrote set 2 (20 new requests) AFTER the patch: 10 of 20 miss a needed tool both on main and with the patch, and all 17 missing tools are vocabulary gaps again. So phrase patching fixes the wordings it targets and does not generalise: this is the honest finding of PLAN-043. Both sets are kept as replay tests (set 2 is a pin that may only go down; it must not be used to patch).
- What would change this (not built, needs the owner): (1) real long prompts to replace the assistant-written sets; (2) a semantic match, rejected earlier for an offline plugin but the only thing that closes "colour by count" to a graduated style without a phrase; (3) lean on find_tools (rule 56) for the misses and measure with a real model whether it calls it. Option D (bigger k) would not help either: the missing tools score below the floor, not below the cut.
