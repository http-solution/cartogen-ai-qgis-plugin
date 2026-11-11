"""Which persona the user is: one stored choice instead of two lists (PLAN-023 R1-2). Pure Python; the settings store is passed in, so it is tested with a plain fake.

Before this, two unrelated lists existed: the refinement persona (15 sectors, a Settings dropdown) and the onboarding role (7 roles, a sentence in the profile file). Now the persona pack (this package) is the
only list. The user's choice is `persona_primary` (the one whose tools the router ranks higher and whose guidance the refiner uses) and an optional `persona_secondary` (ranked at half weight, R1-4).
The onboarding role stays, because it feeds the sentence in the base prompt and the profile file, but it is mapped to a persona id (ROLE_TO_PERSONA) so a person who only ever did the onboarding gets a
sensible default.

First read migrates, once, and writes the result back: an existing `cartogen_ai/user_profile` value (the old Settings dropdown) becomes the primary persona unchanged; with no old value the role of a
finished onboarding is mapped; else `general`. The old key is kept as a mirror of the primary so nothing that still reads it breaks. The secondary is never guessed: it is empty until the user picks one."""
from ..logger import log_event
from . import ids as persona_ids

PRIMARY_KEY = "cartogen_ai/persona_primary"
SECONDARY_KEY = "cartogen_ai/persona_secondary"
LEGACY_KEY = "cartogen_ai/user_profile"           # the old Settings dropdown (SETTINGS_USER_PROFILE); kept in step with the primary
DEFAULT_PERSONA = "general"

# onboarding_profile.ROLE_CHOICES key -> persona id. Roles with no sector of their own map to the generalist.
ROLE_TO_PERSONA = {
    "humanitarian_analyst": "humanitarian",
    "emergency_responder": "humanitarian",
    "urban_planner": "urban_planning",
    "researcher": "research",
    "cartographer": "general",
    "gis_student": "general",
    "other": "general",
}


def _valid(value):
    return isinstance(value, str) and value in persona_ids()


def resolve_selection(primary=None, secondary=None, legacy_profile=None, role=None):
    """(primary, secondary, migrated): the persona selection to use from whatever is stored. `legacy_profile` is the old dropdown value or None when that key was never set (an unset key must not
    count as a choice of 'general'); `role` is the onboarding role key or None. migrated is True when the stored primary was missing or invalid, so the caller writes the result back. Pure."""
    migrated = not _valid(primary)
    if not migrated:
        chosen = primary
    elif _valid(legacy_profile):
        chosen = legacy_profile
    elif ROLE_TO_PERSONA.get(role) and ROLE_TO_PERSONA[role] != DEFAULT_PERSONA:
        chosen = ROLE_TO_PERSONA[role]
    else:
        chosen = DEFAULT_PERSONA
    second = secondary if _valid(secondary) and secondary != chosen else ""
    return chosen, second, migrated


def read_selection(settings, role=None):
    """(primary, secondary) from a settings object with value(key, default) and setValue(key, value), migrating and writing back on the first read. Never raises: a store that fails reads as the
    defaults. `role` is the onboarding role key, only used when migrating."""
    try:
        primary, secondary = settings.value(PRIMARY_KEY, None), settings.value(SECONDARY_KEY, None)
        legacy = settings.value(LEGACY_KEY, None)
    except Exception as e:
        log_event("persona_settings_unreadable", tag="Personas", error_class=type(e).__name__, error=True)
        return DEFAULT_PERSONA, ""
    chosen, second, migrated = resolve_selection(primary, secondary, legacy or None, role)
    if migrated:
        try:
            write_selection(settings, chosen, second)
        except Exception as e:
            log_event("persona_settings_unwritable", tag="Personas", error_class=type(e).__name__, error=True)
            return chosen, second          # still usable this session; written again next time
    return chosen, second


def write_selection(settings, primary, secondary=""):
    """Store the choice (an unknown id is stored as the default / none) and mirror the primary into the old key. Returns (primary, secondary) as stored."""
    chosen, second, _ = resolve_selection(primary, secondary)
    settings.setValue(PRIMARY_KEY, chosen)
    settings.setValue(SECONDARY_KEY, second)
    settings.setValue(LEGACY_KEY, chosen)
    return chosen, second
