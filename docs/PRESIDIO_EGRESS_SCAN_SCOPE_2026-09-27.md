# Outbound PII scanning (Presidio) — scoped, not recommended

**Status: scoping document, not a build plan.** Alaa asked to scope `Presidio` (Microsoft) as
outbound content-based PII detection on top of `core/models/egress_gate.py`, the existing
tag-and-lineage cloud egress gate (`docs/OLLAMA_ENFORCEMENT_GATE_SCOPE_2026-09-24.md`, `SECURITY.md`
"The Ollama-only constraint..."). This scopes it the way `docs/RESTRICTEDPYTHON_SANDBOX_LAYER_SCOPE_2026-09-27.md`
scoped RestrictedPython: install the real library, run it live against this project's own real
content, and report what was actually found — not what the library's own marketing claims.

**The short version: this project already considered and rejected this exact option, and live
testing here confirms the rejection was right — worse than the original reasoning anticipated, not
better.**

## 1. This was already scoped once, and rejected

`docs/OLLAMA_ENFORCEMENT_GATE_SCOPE_2026-09-24.md` §4 lists four candidate mechanisms for the
egress gate and explicitly names this one:

> **G4 — content detection/redaction on egress** (regex/NER for names, phone numbers,
> coordinates). Unreliable in exactly the cases that matter (transliterated Arabic names,
> household IDs, coordinate precision) and it creates false assurance. Not recommended as the
> boundary; at most a secondary warning.

The gate that was actually built (`egress_gate.py`, G1/G2: tag-and-lineage) says the same thing
in its own docstring: *"the scope doc's G4 for why content detection was rejected"* is cited
directly in `evaluate_attachment()`'s docstring as the reason an attached file's content is never
inspected — it's treated like an untagged layer instead.

This document's job was to check whether `Presidio` specifically changes that verdict — a real
library might do better than the "regex/NER" the original doc reasoned about in the abstract. It
does not. The rest of this document is the live evidence.

## 2. What was actually tested

`presidio-analyzer` v2.2.364 (current on PyPI) installed in a clean virtualenv, with its default
English pipeline (`en_core_web_lg`, spaCy's largest English NER model, ships as a **~400MB**
download on its own) run against text shaped like this project's own real data — humanitarian
incident/beneficiary records, matching the ACLED/IMSMA-style content this plugin's own tools
(`fetch_*` hazard tools, `add_point_layer`, sensitivity tagging) actually handle:

```python
from presidio_analyzer import AnalyzerEngine
analyzer = AnalyzerEngine()
analyzer.analyze(text="...", language="en")
```

| Input | Detected | Verdict |
|---|---|---|
| `"Please check on John Smith at his registered address."` | `PERSON: "John Smith"` (0.85) | Correct — the case Presidio is built for. |
| `"Beneficiary Mohammed Al-Khalil reported needing shelter."` | `PERSON: "Beneficiary Mohammed Al-Khalil"` (0.85) | Wrong span — swallowed the preceding word "Beneficiary" into the flagged name. Redaction on this span would still catch the real name, but the span itself is wrong. |
| `"المستفيد هو محمد الخليل ويحتاج إلى مأوى."` (Arabic script: "The beneficiary is Mohammed Al-Khalil and needs shelter.") | `PERSON: "المستفيد"` (= "the beneficiary", **not a name**) and `PERSON: "الخليل ويحتاج"` (a garbled fragment spanning part of the real name plus the next word) | **Actively wrong, not just missed.** Flags an ordinary word as a name while mangling the real name's boundaries. English NER has no real signal on Arabic script (no letter case, different name-boundary cues) and is effectively guessing. |
| `"Household ID HH-2026-00432 was flagged for follow-up."` | nothing | Missed entirely — no built-in recognizer for this kind of domain identifier; would need a fully custom regex recognizer, unbuilt here or anywhere upstream. |
| `"The incident occurred at 33.5138, 36.2765 near the border."` | `PHONE_NUMBER: "36.2765"` (0.4) | **Actively wrong.** A coordinate got relabeled as a phone number. Presidio ships no coordinate/GPS entity recognizer at all — this isn't a tuning gap, the entity type doesn't exist by default. |
| `"Contact number is +963 944 123 456 for the field team."` | `PHONE_NUMBER: "+963 944 123 456"` (0.75) | Correct. |
| Combined realistic sentence (name + phone + household ID + coordinates in one sentence) | Name and phone caught; household ID and coordinates both silently missed once mixed into a longer sentence | The two entity types this project's own data actually needs protecting (identifiers, coordinates) are exactly the two that don't work. |

**Retested with a multilingual model** (`xx_ent_wiki_sm`, spaCy's small multilingual NER,
configured per Presidio's own `NlpEngineProvider` multi-language setup) specifically to check
whether the English-model failure above was just "wrong model," not "wrong approach":

| Input | Detected |
|---|---|
| `"المستفيد هو محمد الخليل ويحتاج إلى مأوى."` (contains a real name) | **Nothing** — missed the name entirely. |
| `"تم تسجيل فاطمة يوسف في المخيم رقم خمسة."` ("Fatima Youssef was registered in camp number five" — contains a real name, "camp number five" is not one) | `PERSON: "المخيم رقم خمسة"` (= "camp number five", **not a name**) — the real name `"فاطمة يوسف"` (Fatima Youssef) was missed completely. |

Switching to a multilingual model did not fix the Arabic-script case — it's a different failure
shape (misses instead of mangles), not a working one.

## 3. What this confirms and sharpens

The original G4 rejection said "unreliable in exactly the cases that matter." The live evidence
here is stronger than "unreliable": on this project's actual highest-stakes data — a beneficiary's
name in Arabic script, the language this plugin's own humanitarian-GIS use case (Syria/MENA field
mapping, per `CLAUDE.md`'s own framing) is centered on — Presido doesn't degrade gracefully to
"catches less." It produces **confidently wrong output**: real names missed, ordinary words and
phrases flagged as PERSON, a coordinate mislabeled as a phone number. A user or reviewer glancing
at "PII detected: none" on an Arabic-language incident report would have exactly zero signal that
anything was checked at all, and "PII detected: camp number five" actively erodes trust in the
tool making the check.

This is the "false assurance" half of the original rejection, now demonstrated rather than
predicted: shipping this as a stated privacy control while it does this poorly on the project's
own primary language would be worse than not having it, because a data-protection officer or a
field user would reasonably read "no PII found" as an actual finding rather than as an artifact of
the detector not understanding the script it was reading.

## 4. What Presidio does not change about the gate's actual gap

`SECURITY.md`'s own "What it does not do" list for the egress gate names two things not gated
today: **text the user types or pastes**, and **the model repeating in its own prose what it saw
earlier**. Those are the routes G4 would have to cover to matter — the tag-and-lineage gate
already covers tool calls and (in strict mode) attachments. Given §2 and §3 above, plugging
Presidio into either of those two routes would not close them in any way that survives contact
with this project's actual data; it would add a new dependency (a ~400MB model download, on top
of `spacy`/`presidio-analyzer` themselves) and real latency per message, in exchange for a control
that's wrong specifically on the content this plugin's own humanitarian use case cares about most.

## 5. Recommendation

**Do not build this.** Not "defer," the way Shape B was deferred in the RestrictedPython doc —
the live evidence here is a reason to actively not adopt Presidio for this gate, not a reason to
wait for a better moment. If Alaa or a DPO review ever wants a secondary, clearly-labeled-as-
imperfect warning specifically for **English-language** free text (where the one clean result in
§2 — plain Latin-script names and phone numbers — held up), that's a much narrower, English-only
opt-in feature, not the "outbound PII scanning" this document was asked to scope, and it would
need its own explicit framing so it never appears to a user as a real privacy guarantee it can't
back up for the majority of this project's actual beneficiary-data content.

The tag-and-lineage gate (`egress_gate.py`, G1/G2) remains the actual mechanism, unchanged by this
document. The two gaps `SECURITY.md` already names honestly (user-typed text, model-repeated
prose) stay open and undocumented-as-solved — this document does not propose closing them; it
confirms that Presidio specifically is not how to close them.

## 6. What was and wasn't verified

- Verified live: presidio-analyzer v2.2.364's actual detection output on realistic text in both
  its default English configuration and a multilingual configuration, shown inline above, not
  taken from Presidio's own documentation or marketing.
- Not tested: Presidio's commercial/larger transformer-based NER backends (e.g. a
  `transformers`-based recognizer using a larger multilingual model than `xx_ent_wiki_sm`), which
  might do better on Arabic script at a real cost in dependency weight and latency this document
  did not measure. Flagged as a real gap in this analysis, not assumed to also fail — a specific,
  named humanitarian/Arabic-NLP model (e.g. one of CAMeL Lab's Arabic NER models) is the more
  promising direction than a generic multilingual model if this is ever revisited, but that is a
  materially different, heavier proposal than "add Presidio," and not scoped here.
- `presidio-analyzer` and both spaCy models were removed from this environment after testing; none
  of this is a new dependency of this repo.
