"""Persona re-rank of the offered tools (PLAN-023 R1-4), pure Python.

The router scores every tool against the request and offers the best top_k (40). A persona may nudge that choice: the tools in the primary persona's `tool_priority` get a bonus (full), the secondary's
(half), and a persona alias phrase found in the request (`tool_aliases`) counts double. Three rules keep it a nudge and not a takeover:
  * a tool is boosted only if it already scored as relevant to THIS request (score at or above the floor); a persona never adds a tool the request has nothing to do with;
  * at most PERSONA_BOOST_SLOTS tools may enter the offered set because of the boost; when more would, the best-boosted five enter and the others stay out, and the same number of the lowest-ranked
    ordinary tools are the ones displaced (the higher-ranked ordinary tools, and every always-included tool, which scores 1000, are never touched);
  * nothing is ever removed from the registry or made unavailable: a tool the router did not offer can still be found with find_tools or named in the request.
The `general` persona and an unknown or missing persona boost nothing, so a user who never picks one gets exactly the previous behaviour."""
from .. import personas

PERSONA_BOOST_SLOTS = 5
FULL_BONUS = 3.0
SECONDARY_WEIGHT = 0.5
ALIAS_MULTIPLIER = 2.0
NO_BOOST_PERSONAS = ("general", "", None)


def build_bonuses(primary, secondary, query_lower):
    """{tool name: bonus} for the chosen personas and this (lower-cased) request. Pure."""
    out = {}
    for persona_id, weight in ((primary, 1.0), (secondary, SECONDARY_WEIGHT)):
        if persona_id in NO_BOOST_PERSONAS:
            continue
        persona = personas.get(persona_id)
        if persona is None:
            continue
        for name in persona["tool_priority"]:
            out[name] = max(out.get(name, 0.0), FULL_BONUS * weight)
        for name, phrases in persona["tool_aliases"].items():
            if any(str(phrase).lower() in query_lower for phrase in phrases):
                out[name] = max(out.get(name, 0.0), FULL_BONUS * ALIAS_MULTIPLIER * weight)
    return out


def _name(tool):
    return tool.get("function", {}).get("name", "")


def select_tools(scored, top_k, floor, bonuses, slots=PERSONA_BOOST_SLOTS):
    """The tool schemas to offer, from `scored` = [(score, tool)] sorted by score descending (the router's own order). Without bonuses this is exactly the router's old slice:
    the first top_k whose score is at least `floor`. With bonuses see the module docstring. Pure."""
    base = [(s, t) for s, t in scored[:top_k] if s >= floor]
    if not bonuses:
        return [t for _, t in base]
    boosted = [((s + bonuses.get(_name(t), 0.0)) if s >= floor else s, i, t) for i, (s, t) in enumerate(scored)]
    boosted.sort(key=lambda row: (-row[0], row[1]))
    with_boost = [(b, i, t) for b, i, t in boosted[:top_k] if scored[i][0] >= floor]
    base_names = {_name(t) for _, t in base}
    newcomers = [row for row in with_boost if _name(row[2]) not in base_names]
    kept = {_name(row[2]) for row in newcomers[:slots]}
    final = [row for row in with_boost if _name(row[2]) in base_names or _name(row[2]) in kept]
    chosen_names = {_name(row[2]) for row in final}
    index = {id(t): i for i, (_, t) in enumerate(scored)}
    for _, t in base:                                     # top up from the ordinary ranking, best first, so at most `slots` ordinary tools are displaced
        if len(final) >= len(base):
            break
        if _name(t) not in chosen_names:
            final.append((scored[index[id(t)]][0], index[id(t)], t))
            chosen_names.add(_name(t))
    final.sort(key=lambda row: (-row[0], row[1]))
    return [t for _, _, t in final]
