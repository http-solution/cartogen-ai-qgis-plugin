"""The readiness panel text (PLAN-023 R1-3), pure Python: what the plugin can and cannot do for the chosen persona(s), generated from the persona files so the screen can never say more than the files do.

The Settings and onboarding pickers show this text under the two persona dropdowns. Headings, in this order, only when they have entries:
  Built and seen working        capabilities a live run saw working (none until docs/LIVE_RESULTS.json records one)
  Available (checked by tests)  the tool exists and an automatic test covers it; no person has necessarily seen it on real data
  Not built yet                 with the release of docs/plans/PLAN-023 that will deliver it
  Out of scope / Declined       with the reason
The secondary persona, when chosen, follows the primary under its own title. No persona hides or blocks a tool: the text says so once at the end."""
from . import get

HEADINGS = (("built", "Built and seen working"), ("CI-checked", "Available (checked by automatic tests)"), ("not built", "Not built yet"), ("out of scope", "Out of scope"), ("declined", "Declined"))
NOTE = "Every tool stays available whichever persona is chosen; the choice only changes which tools are suggested first and how the assistant words its guidance."


def _line(item):
    text = item["capability"]
    state = item["state"]
    if state == "not built":
        text += f" - due in {item['since']}"
        if item.get("reason"):
            text += f" ({item['reason']})"
    elif state in ("out of scope", "declined"):
        text += f" - {item['reason']}"
    elif item.get("tool"):
        text += f" [{item['tool']}]"
    return text


def sections(persona):
    """[(heading, [line, ...])] for one persona dict, in HEADINGS order, empty groups left out. Pure."""
    out = []
    for state, heading in HEADINGS:
        lines = [_line(item) for item in persona["readiness"] if item["state"] == state]
        if lines:
            out.append((heading, lines))
    return out


def persona_text(persona_id, title=None):
    """The text block of one persona, or '' for an unknown id. Pure."""
    persona = get(persona_id)
    if persona is None:
        return ""
    parts = [f"{title or persona['label']}: {persona['label']}" if title else persona["label"], persona["summary"]]
    for heading, lines in sections(persona):
        parts.append(f"{heading}:")
        parts.extend(f"  - {line}" for line in lines)
    if persona.get("guardrails"):
        parts.append("The assistant will:")
        parts.extend(f"  - {g}" for g in persona["guardrails"])
    return "\n".join(parts)


def panel_text(primary, secondary=""):
    """The full panel for the chosen primary and optional secondary persona (ids). Pure."""
    blocks = [persona_text(primary, "Primary")]
    if secondary and secondary != primary:
        blocks.append(persona_text(secondary, "Secondary"))
    blocks = [b for b in blocks if b]
    return ("\n\n".join(blocks) + "\n\n" + NOTE) if blocks else ""
