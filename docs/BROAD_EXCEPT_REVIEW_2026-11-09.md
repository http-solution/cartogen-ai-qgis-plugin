# Broad exception handlers: review snapshot, 2026-11-09 (DEF-8)

A dated snapshot (not edited later). Produced by `python tools/broad_except_review.py` (new, standard library only); `tests/test_broad_except_review.py` pins the result so it can only shrink.

## Counts (src/, 551 broad handlers)

| Class | What the handler does | Count |
|---|---|---|
| reraises | raises again | 11 |
| uses_error | reads the caught error (message, log, result) | 321 |
| logs | logs without reading the error | 0 |
| returns | returns or sets a value; neither logs nor reads the error | 219 |
| silent | only pass, continue or break | 0 |

`contextlib.suppress(Exception)` blocks, silent by construction and the project's chosen form for best-effort work: 150.

The master list said 504 broad handlers and "none silent". The classifier finds 551 (it also counts bare `except:` and tuple forms) and confirms none is silent in the sense of a body that is only `pass`, `continue` or `break`. The pin keeps it that way.

## What needs a person's review: the 219 "returns" handlers

114 of them return only an empty default (None, False, 0, an empty list or dict) and nothing else, so the failure leaves no trace in the log. Most are deliberate best-effort probes. The ten largest groups by file:

| File | Handlers |
|---|---|
| `src/cartogen_ai/core/agent/tools/humanitarian_style.py` | 13 |
| `src/cartogen_ai/core/agent/tools/_snapshot_registry.py` | 10 |
| `src/cartogen_ai/core/agent/tools/logistics_tools.py` | 7 |
| `src/cartogen_ai/core/agent/agent_orchestrator.py` | 6 |
| `src/cartogen_ai/core/agent/tools/output_style.py` | 6 |
| `src/cartogen_ai/core/agent/tools/raster_tools.py` | 5 |
| `src/cartogen_ai/infrastructure/providers/base.py` | 5 |
| `src/cartogen_ai/core/agent/local_data_loader.py` | 4 |
| `src/cartogen_ai/core/agent/tools/layout_export_checks.py` | 4 |
| `src/cartogen_ai/core/agent/tools/vector_tools.py` | 4 |

## What was reviewed, and what was not

- Read line by line: the 10 handlers of `_snapshot_registry.py`. They are the undo snapshot and restore steps. Each returns `None` or `False` when a snapshot or restore cannot be made, and the callers turn that into a plain "cannot undo" answer; `field_holds_values` returns `True` on error, which is the safe side (it refuses to delete a field it cannot read). They are intended. They log nothing, so a user sees the refusal but the log does not say why.
- Not reviewed line by line: the other 209 "returns" handlers. Reading them all is a day of work with a decision per handler; this snapshot only makes the list exact.

## Recommendation

1. Leave the pin as it is. It blocks the one clearly bad pattern and stops the list growing.
2. When one of these files is next changed for another reason, add a `log_event("swallowed_exception", ...)` line to its handlers (the form already used in `agent_orchestrator.py`) and lower `MAX_SWALLOW_AND_RETURN`.
3. Do not rewrite them in one sweep: several guard optional QGIS features whose absence is normal, and a log line per probe would flood the log.
