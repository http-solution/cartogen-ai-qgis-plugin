# Decision aid: should a large download be confirmed by you, not by the model? (RM-C, 2026-11-23)

Written for the owner. Plain language. Nothing here changes code; it needs your choice first.

## What is true today (checked in the code, not from memory)

- **Three fetch tools have a size guard:** geoBoundaries, HDX boundaries and building footprints. Before downloading, the plugin asks the server how big the file is. Above your "Ask before downloads larger than" setting (50 MB by default) it stops and returns an error that tells the model: "tell the user the size and ask; if they agree, call again with `allow_large_download=true`."
- **The weak point:** that `true` is a setting the model can send by itself. The tool description says "only after the user agreed", but nothing checks that you did. A model that skips the question (or a weak one) downloads the file anyway. This is an honour system.
- **Other downloads are already firm:** `fetch_dem` and `load_stac_assets` show a preview card with the size, and nothing downloads until you press Apply (the model cannot press it). OSM extracts and WorldPop have their own confirmations. Write tools use the same card.
- **No size check at all:** the five event feeds (NASA fires, NASA EONET, GDACS, USGS, UCDP). They return small lists limited by days or area, so I treat them as out of scope here.
- **Not verified:** none of this was tried by a person at a real card for the three guarded tools. The card mechanism itself is used and tested for other tools.

## The choice

| Option | What you see | Safe against a model that skips the question? | Work and risk |
|---|---|---|---|
| **A. Leave as is** | The model asks you in chat, if it remembers to. | No. | None. |
| **B. Use the same Apply card** (recommended) | A card: "geoBoundaries ADM2 for YEM is about 120 MB (source, licence, area). Download?" Apply or cancel. | Yes: the model cannot press Apply. | Small to medium. It reuses the card mechanism the STAC and DEM tools already use. Most of it is testable offline; how the card looks is only visible in QGIS. |
| **C. B plus a look at the data before it loads** | The card, and after download a second step showing feature count and extent before the layer is added. | Yes. | Medium. A second prompt on every large fetch; I think it adds friction for little gain, because the size, source and area are already on the first card. |
| **D. Refuse above a fixed ceiling** | An error, no way to override. | Yes. | Small, but it blocks legitimate large downloads. |

## Recommendation

**Option B.** It closes the only real gap (the model can approve its own large download) with a mechanism you already use and trust elsewhere. I would put the licence line from the source record on the card, so the same step shows where the data comes from and under what terms. I would keep the 50 MB setting as the trigger.

What I would do after your go: change the three guarded tools to return the Apply card instead of the "ask the user" error, keep `allow_large_download` accepted only from the confirmed Apply call, add tests that the model cannot self-approve, and list the live-QGIS check in the hand rows. It would stay CI-checked and not hand-tested until a person sees the card.

## What I need from you

One word: **A, B, C or D**. If B, also say whether the five event feeds should get a card too (I recommend no).
