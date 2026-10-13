---
description: Exactly what the plugin sends to a model provider and to public data services, what stays on your machine, and the settings that limit it.
---
**Short version.** Everything you type, and what the tools it calls surface, goes to the model provider you chose, using your own key. If that is **Ollama**, nothing leaves your machine. Nothing is sent to the Cartogen project: there is no Cartogen server in the loop.

## What goes to the model provider (cloud)

| Sent | Detail |
|---|---|
| **Your request text** | Including the prompt the preview showed you, or your own wording. |
| **Map context** | Up to 15 layers: name, type, CRS, feature count, up to 8 field names each, and the active layer. Sent **every turn**. |
| **Tool results** | What a tool returns that the model needs to answer: attribute values, counts, statistics, coordinates, table rows. |
| **Conversation so far** | Your earlier messages and the assistant's final replies (not raw tool results). |
| **Your profile and project memory** | The role and style answers from `user_profile.md` and any project notes, in the system prompt. |
| **Attachments** | A file you attach is classified and read; its extracted content is carried into the request. |
| **Optional second send** | If the prompt refiner is on, your raw message goes to the provider an extra time. |

The provider processes this under its own terms. Settings shows each cloud provider's Data Processing Addendum link as a starting point. **Whether you may send the data at all is your organisation's responsibility**: the plugin cannot determine a lawful basis or transfer mechanism for you. Read the data-protection section of [the full threat model](@security/policy) and, for real beneficiary data, your DPO's determination. The repository's DPIA determination may restrict which provider you can use for which data, for example requiring Ollama for anything touching protection, incident or displacement attributes. **The plugin does not enforce that restriction unless you turn on the egress gate.**

## What goes to public data services

Fetch tools call public services **directly from your machine**, not through the model: bounding boxes and place names go to Overpass, Nominatim, HDX, geoBoundaries, USGS, GDACS, EONET, UCDP, ReliefWeb, STAC, WorldPop, NASA and similar. Those services see your IP address and the query. The full list, with which tools read which service, is on [External data sources](@reference/data-sources). `search_web` sends a search query to a search provider; Gemini grounded search sends it to Google.

## What the limiting settings do

| Setting | Effect | Default |
|---|---|---|
| **Provider = Ollama** | Nothing leaves your machine. | n/a |
| **Layer sensitivity tags** (dialog) | You mark a layer SENSITIVE, RESTRICTED, INTERNAL or PUBLIC. Only you can change a tag; the model cannot. | untagged |
| **Egress gate**: off / warn / enforce | With a non-local provider, block (enforce) or warn about a tool call or attachment that touches a protected layer; in enforce also withholds that layer's field names from the map context. Follows layer lineage through renames and duplicates. | **off** |
| **Plan gate** | Plan required for DELETE and PUBLISH calls. | off |
| **Prompt preview** | Shows the exact prompt before it is sent. | on |
| **Save the conversation in the project file** | Stores the transcript in the `.qgz`; a shared project carries it. | **on** |
| **API trace**, **Evidence folder** | Store raw requests, replies and results on your disk. Check them before sharing. | off |

The egress gate does **not** cover the model repeating in its prose something it saw earlier, or text you type or paste into the chat.

## What stays on your machine

- **Task matching** against the register is local; the register is never sent.
- **Keys** live in QGIS's encrypted Auth Manager (or session memory), never plaintext on disk, and never in logs.
- **Logs** record event names and metadata only: never prompts, replies, tool arguments or results, coordinates or keys; key-shaped strings are redacted.
- **Memory, profile, results store, evidence and trace** are local files. The Memory dialog exports and deletes memory and the saved chat; **Export My Data** writes a consolidated portable copy.

## Not done, said plainly

- **No data minimisation or redaction** is built into the tool-calling path: the plugin does not know what counts as personal or special-category data in your context, which is a legal judgement, not an engineering one.
- **No hosted, private-enclave option** exists. Every request goes straight from your machine to the provider you configured.
- **The 2026-09-01 GDPR review and DPIA worksheet** are code-level starting points, not legal sign-off: see [GDPR compliance review](https://github.com/http-solution/cartogen-ai-qgis-plugin/blob/main/docs/GDPR_COMPLIANCE_REVIEW.docx), [DPIA screening worksheet](https://github.com/http-solution/cartogen-ai-qgis-plugin/blob/main/docs/DPIA_SCREENING_WORKSHEET.docx) and the [hosted-account addendum](repo:docs/GDPR_HOSTED_ACCOUNT_ADDENDUM_2026-09-08.md).
