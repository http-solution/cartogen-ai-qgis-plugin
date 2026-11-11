"""Persona pack loader and checker (PLAN-023 R1-1; design in docs/PERSONA_TOOLS_STYLING_PLAN_2026-10-04.md section 3).

A persona is one JSON file in this folder, named <id>.json. It says, for one kind of user, what the plugin can and cannot do for them today, so the picker, the prompt, the router and the
documentation all read the same facts instead of four separate lists. A persona NEVER hides or blocks a tool and carries no tier logic (CLAUDE.md, editions): `tool_priority` only lets the router
rank some tools higher, and `readiness` only describes.

Fields (all required): id, number (1 to 15, the order of PROFILE_LABELS), label, aliases, summary, guidance, workflows [{id, title, tools}], tool_priority (at most 12 tool names), tool_aliases
{tool: [phrases]}, task_ids (ids of the task register; filled by R1-5), data_sources (ids; checked against data_sources.json when R1-8 adds it), style_profile (id; checked against the style
profiles when R1-7 adds them), layout_templates, readiness [{capability, state, tool?, since?, reason?, hand_row?}], guardrails.

`readiness` states, and what each may claim:
  built        a person saw the capability work in a live QGIS run (it names the ledger feature whose entry in docs/LIVE_RESULTS.json is "working");
  CI-checked   the tool exists and an automatic test, usually in a real QGIS in CI, covers it, but no person has seen it work on real data: the honest default for everything built since 1.18;
  not built    named with the release of docs/plans/PLAN-023 that will deliver it (`since`);
  out of scope the plugin will not do it, with the reason;
  declined     considered and refused, with the reason.
validate() is pure and returns the problems as readable strings; tests/test_personas.py fails on any."""
import json
from pathlib import Path

FOLDER = Path(__file__).resolve().parent
STATES = ("built", "CI-checked", "not built", "out of scope", "declined")
MAX_PRIORITY = 12
REQUIRED = ("id", "number", "label", "aliases", "summary", "guidance", "workflows", "tool_priority", "tool_aliases", "task_ids", "data_sources", "style_profile",
            "layout_templates", "readiness", "guardrails")

_CACHE: dict = {}


def load_all():
    """{persona id: dict} for every <id>.json in this folder, in persona-number order. Cached."""
    if not _CACHE:
        found = {}
        for path in FOLDER.glob("*.json"):
            found[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        _CACHE.update(dict(sorted(found.items(), key=lambda kv: kv[1].get("number", 99))))
    return dict(_CACHE)


def ids():
    return list(load_all())


def get(persona_id):
    """The persona with this id, or None."""
    return load_all().get(persona_id)


def tools_named(persona):
    """The set of tool names one persona dict mentions anywhere: priority list, alias keys, workflow steps and readiness lines. Pure. Used by the catalogue and the reachability ratchet
    (PLAN-023 R1-6) so both read a persona the same way."""
    named = set(persona["tool_priority"]) | set(persona["tool_aliases"]) | {t for w in persona["workflows"] for t in w.get("tools", [])}
    return named | {r["tool"] for r in persona["readiness"] if r.get("tool")}


def validate(persona, tool_names=None, task_ids=None, working_features=None, style_profile_ids=None):
    """Problems with one persona dict as a list of readable strings (empty = fine). `tool_names` is the set of registered tools, `task_ids` the task-register ids and `working_features` the
    ledger features a live run saw working and `style_profile_ids` the keys of representation/style_profiles.PROFILES (R1-7); a check that needs one is skipped when it is None. Pure."""
    pid = persona.get("id", "?")
    problems = [f"{pid}: missing field '{key}'" for key in REQUIRED if key not in persona]
    if problems:
        return problems
    if not isinstance(persona["number"], int) or not 1 <= persona["number"] <= 15:
        problems.append(f"{pid}: number must be a whole number from 1 to 15")
    problems.extend(f"{pid}: '{key}' is empty" for key in ("label", "summary", "guidance") if not str(persona[key]).strip())
    if len(persona["tool_priority"]) > MAX_PRIORITY or len(set(persona["tool_priority"])) != len(persona["tool_priority"]):
        problems.append(f"{pid}: tool_priority must list at most {MAX_PRIORITY} different tools")
    named = list(persona["tool_priority"]) + list(persona["tool_aliases"]) + [t for w in persona["workflows"] for t in w.get("tools", [])]
    named += [r["tool"] for r in persona["readiness"] if r.get("tool")]
    if tool_names is not None:
        problems += [f"{pid}: tool '{t}' is not a registered tool" for t in sorted(set(named)) if t not in tool_names]
    if style_profile_ids is not None and persona["style_profile"] not in style_profile_ids:
        problems.append(f"{pid}: style_profile '{persona['style_profile']}' is not in the style profile registry")
    if task_ids is not None:
        problems += [f"{pid}: task id '{t}' is not in the task register" for t in persona["task_ids"] if t not in task_ids]
    for w in persona["workflows"]:
        if not (w.get("id") and w.get("title") and w.get("tools")):
            problems.append(f"{pid}: a workflow needs an id, a title and tools")
    problems.extend(p for item in persona["readiness"] for p in _check_readiness(pid, item, working_features))
    if not persona["guardrails"] or not all(str(g).strip() for g in persona["guardrails"]):
        problems.append(f"{pid}: guardrails must list at least one statement")
    return problems


def _check_readiness(pid, item, working_features):
    name = item.get("capability", "?")
    state = item.get("state")
    if state not in STATES:
        return [f"{pid}: '{name}' has the state {state!r}; use one of {', '.join(STATES)}"]
    if state in ("CI-checked", "built") and not item.get("tool"):
        return [f"{pid}: '{name}' is {state} but names no tool"]
    if state == "not built" and not item.get("since"):
        return [f"{pid}: '{name}' is not built but names no release in 'since'"]
    if state in ("out of scope", "declined") and not item.get("reason"):
        return [f"{pid}: '{name}' is {state} but gives no reason"]
    if state == "built" and (not item.get("feature") or (working_features is not None and item["feature"] not in working_features)):
        return [f"{pid}: '{name}' is built but no live run saw feature '{item.get('feature')}' working"]
    return []
