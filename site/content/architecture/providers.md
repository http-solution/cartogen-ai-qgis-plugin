---
description: The model provider clients, automatic model selection, retries and fallbacks, and how every network request goes through QGIS.
---
## Providers

All providers implement `BaseAiProvider.complete(messages, tools, max_tokens)` in `infrastructure/providers/base.py`, so the agent loop does not know which one it is talking to.

| Provider | File | Status |
|---|---|---|
| **OpenRouter** | `openrouter.py` | Offered. Has a free tier covering many models. |
| **Google Gemini** | `gemini.py` | Offered. Native web-search grounding; automatic model fallback list `gemini-flash-latest`, `gemini-3.8-flash`, `gemini-3.7-flash`. |
| **Ollama** | `ollama.py` | Offered. A local server: nothing leaves the machine, no key. Long timeout (180 s per call). |
| **Cartogen API** | `cartogen.py` | A **stub**. No hosted gateway is deployed, so it cannot be used; the module says so and is not wired into anything. |
| OpenAI, Claude | `openai.py`, `claude.py` | Code kept, **not offered** since rc25 because they were never tested. A provider saved by an older version falls back to OpenRouter and its saved settings are left alone. |

The provider list is normalised in `settings_keys.py`; Settings and the quick-switcher offer only the first three (plus the stub entry).

## Choosing a model

Leave the model on **Auto** and `model_selector.py` picks between a cheaper, faster model and a more capable one from whatever the provider's **live model list** returned, based on the request's wording and length. It never invents a model id. Ollama always uses the model you pick. If a configured model is retired (Google answers 404), the provider falls through its fallback chain.

## Retries, quotas and refusals

`base.py` retries transient failures (429, 500, 502, 503, 504) with a short budget, and gives 429 its own longer backoff. Some failures should not be retried, and since rc34 are not:

- a quota of **zero** (the free tier has none for Pro models) is returned immediately and the next model is tried;
- a model refused with **403** is skipped;
- when the whole project is denied, the plugin stops and shows the provider's own message instead of walking every model.

A refusal message states, for each model tried, the status and the provider's text, which key was sent (length, last four characters and where it was found, never the whole key) and, for an unrecognised reply, the server name and size. Provider text that looks like a key is blanked. See [Troubleshooting](@troubleshooting).

## Token economy

- **Measured:** every call records provider-reported input, cached and output tokens, latency and the tools offered; estimates are labelled and kept apart. Each reply's footer shows what the request used.
- **Cached prefix:** the system prompt keeps its stable part first and the layer list last, and tools are tie-broken deterministically, so providers with implicit prefix caching (Gemini 2.5+) and cache-control breakpoints (OpenRouter) can reuse it.
- **Bounded:** the per-turn token budget (default 450,000) stops a request before a call that would pass it; the round cap (default 20) and the loop guard stop unproductive turns.
- **Fewer round trips:** `run_steps` and the vetted chains batch dependent calls.

## Networking

Plugin directory guidance is to use QGIS's network stack, so the proxy, authentication and SSL settings a user configured in QGIS apply. `core/net.py` and the provider base implement that:

- **Data-fetch tools** call `core.net.urlopen`, a drop-in for `urllib.request.urlopen` built on `QgsBlockingNetworkRequest`, safe on a worker thread. QGIS applies its own timeout (Settings → Options → Network, default 60 s) and sets its own User-Agent.
- **Hosted AI calls** (OpenRouter, Gemini, the Cartogen stub) use `QgsNetworkAccessManager` directly. A request with a body or credential header cannot use the blocking class, because it follows a redirect with a brand-new request and loses the `Authorization` header (reproduced in QGIS 4.2.2). The plugin follows redirects itself: same method, headers and body on 307/308, a plain GET on 301/302/303, the key kept on the same site and dropped for another, at most 5 hops, each logged by host only (rc33).
- **Streamed downloads** (Geofabrik extracts, model checkpoints, URLs the model names) read the reply incrementally through QGIS, so progress, cancel and an idle timeout work, and a cut-short transfer is an error, not a smaller file. The first hop goes through QGIS; further hops are fetched after each is vetted against the private-address rules (`stream_following`).
- **Ollama** stays on the Python `requests` library: it is a loopback server whose answers can take minutes, which QGIS's per-request timeout would cut off, and a local address should not be sent through a corporate proxy.
- Outside QGIS (unit tests, the isolated script worker) the same code falls back to `urllib`/`requests`.
- Remote answers are size-limited (`read_capped`, `gunzip_capped`, `zip_member_capped`): JSON and CSV answers 64 MB, downloads 1.5 GB, and a gzip tile or zip member that would expand past 256 MB is refused.

Setting `cartogen_ai/hosted_requests_via_qgis` to `false` in QGIS's advanced settings sends hosted AI requests the way versions before rc28 did (added in rc32 while a Gemini 403 was being diagnosed).

## Credentials

`infrastructure/auth.py` stores keys in QGIS's **Auth Manager** (encrypted). If it is unavailable or refuses, the key lives in process memory for the session and Settings warns; it is never written to disk in plain text. Keys saved in plain text by old versions are only read and migrated. Logs carry no credential and no exception text; `core/logger.py` redacts key-shaped strings.

## Provider-side search

Gemini's native grounded search is available as `gemini_grounded_search`; a small shared in-memory TTL cache (`_search_cache.py`) avoids repeating billed searches. See [Security overview](@security/overview) for how fetched web text is treated as data, not instructions.
