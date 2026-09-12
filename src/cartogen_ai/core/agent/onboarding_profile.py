# -*- coding: utf-8 -*-
"""
Onboarding profile for Cartogen AI -- a short, narrative first-use questionnaire (role/use-case,
QGIS experience level, communication style), requested directly 2026-09-12 ("optimize the user
profile by creating .md files locally... in a narrative way like introduce yourself and ask the
user to select his profile type").

Deliberately named and keyed differently from prompt_refiner.py's existing "user_profile"
(USER_PROFILE_KEY, get_user_profile()/PROFILE_LABELS) -- that one is the Refinement Persona, a
sector dropdown (e.g. "humanitarian"/"engineering") that only steers the optional prompt-
refinement rewrite feature when it's enabled. This one feeds the BASE system prompt directly
(see prompts.py's build_system_prompt) on every request, refinement enabled or not -- a
genuinely separate concept that happens to share the English word "profile".

Storage is a real, human-readable .md file on disk, not another QgsSettings JSON blob, so it can
be opened, read, and hand-edited like any other local note -- per the direct request above. The
file IS the source of truth (re-read and re-parsed each time it's needed, not cached into
QgsSettings as a shadow copy that could drift). Only "has onboarding ever run" lives in
QgsSettings -- a cheap boolean check at every plugin init shouldn't require opening a file.

QGIS_AVAILABLE-guarded throughout (same convention as memory.py/prompt_refiner.py) so the pure
formatting/parsing logic stays unit-testable without a QGIS install.
"""

import os
import re

try:
    from qgis.core import QgsApplication, QgsSettings
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


ONBOARDING_COMPLETED_KEY = "cartogen_ai/onboarding_completed"

# value -> label. Keys are what gets stored/parsed; labels are what the dialog shows and what
# gets written into the .md file (round-tripped back via _reverse_lookup()).
ROLE_CHOICES = {
    "humanitarian_analyst": "Humanitarian / Crisis Response Analyst",
    "cartographer": "Cartographer / Map Producer",
    "gis_student": "GIS Student / Learner",
    "emergency_responder": "Emergency Responder / Field Operator",
    "urban_planner": "Urban Planner",
    "researcher": "Researcher / Academic",
    "other": "Other",
}
DEFAULT_ROLE = "other"

EXPERIENCE_CHOICES = {
    "beginner": "Beginner -- new to QGIS",
    "intermediate": "Intermediate -- comfortable with everyday QGIS tasks",
    "expert": "Expert -- deep QGIS/GIS background",
}
DEFAULT_EXPERIENCE = "intermediate"

STYLE_CHOICES = {
    "concise": "Concise -- short, to-the-point answers",
    "detailed": "Detailed -- explain reasoning and steps along the way",
    "plain_language": "Plain language -- avoid GIS/technical jargon where possible",
    "technical": "Technical -- comfortable with GIS/technical terminology",
}
DEFAULT_STYLE = "detailed"

_ROLE_LINE = re.compile(r"^-\s*\*\*Role:\*\*\s*(.+)$")
_ROLE_OTHER_LINE = re.compile(r"^-\s*\*\*Role \(other\):\*\*\s*(.+)$")
_EXPERIENCE_LINE = re.compile(r"^-\s*\*\*Experience level:\*\*\s*(.+)$")
_STYLE_LINE = re.compile(r"^-\s*\*\*Communication style:\*\*\s*(.+)$")


def _reverse_lookup(choices, label, default):
    for key, value in choices.items():
        if value == label.strip():
            return key
    return default


def _profile_base_dir():
    """The QGIS active-profile settings directory (e.g.
    .../AppData/Roaming/QGIS/QGIS4/profiles/default/cartogen_ai/) -- global, not per-project,
    matching "who is this user" being a machine-wide fact. Falls back to a home-directory dotfile
    location outside QGIS (tests, or the rare case qgisSettingsDirPath() itself fails), mirroring
    memory.py's _get_db_path() home-dir fallback pattern."""
    if QGIS_AVAILABLE:
        try:
            base = QgsApplication.qgisSettingsDirPath()
            if base:
                return os.path.join(base, "cartogen_ai")
        except Exception:
            pass
    return os.path.join(os.path.expanduser("~"), ".cartogen_ai")


def get_profile_md_path():
    return os.path.join(_profile_base_dir(), "user_profile.md")


def is_onboarding_completed() -> bool:
    """Mirrors chat_persistence.is_persist_enabled()'s exact shape (QGIS_AVAILABLE guard, never
    raises). Defaults False (not yet shown) -- the caller triggers onboarding on False, matching
    "never seen it" and "QGIS unavailable" the same way (nothing to show without QGIS anyway)."""
    if not QGIS_AVAILABLE:
        return False
    try:
        return bool(QgsSettings().value(ONBOARDING_COMPLETED_KEY, False, type=bool))
    except Exception:
        return False


def mark_onboarding_completed():
    """Set once the dialog is dismissed, whether saved or skipped -- skipping still means the
    user has SEEN the offer and chosen not to fill it in; it should not nag again next launch."""
    if not QGIS_AVAILABLE:
        return
    try:
        QgsSettings().setValue(ONBOARDING_COMPLETED_KEY, True)
    except Exception:
        pass


def save_onboarding_profile(role, role_other, experience, style):
    """Writes the narrative .md file and marks onboarding completed. role/experience/style are
    internal keys (e.g. "cartographer", not the label) -- looked up against the *_CHOICES dicts
    above so the file always shows the human-readable label, never a raw key. Returns the path
    written to, mainly for tests/verification. role_other is only included as its own bullet line
    when role == "other" and it's non-empty, keeping the parser simple (one fixed line per field,
    no inline-suffix parsing)."""
    role_label = ROLE_CHOICES.get(role, ROLE_CHOICES[DEFAULT_ROLE])
    experience_label = EXPERIENCE_CHOICES.get(experience, EXPERIENCE_CHOICES[DEFAULT_EXPERIENCE])
    style_label = STYLE_CHOICES.get(style, STYLE_CHOICES[DEFAULT_STYLE])

    lines = [
        "# Cartogen AI -- Your Profile",
        "",
        "This file is read by Cartogen AI to tailor its tone and detail level to how you work. "
        "Edit it directly at any time, or update it via Settings -> Edit My Profile in QGIS.",
        "",
        f"- **Role:** {role_label}",
    ]
    if role == "other" and role_other and role_other.strip():
        lines.append(f"- **Role (other):** {role_other.strip()}")
    lines.append(f"- **Experience level:** {experience_label}")
    lines.append(f"- **Communication style:** {style_label}")
    lines.append("")

    path = get_profile_md_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    mark_onboarding_completed()
    return path


def load_onboarding_profile():
    """Reads the .md file back into a dict of internal keys ({"role", "role_other",
    "experience", "style"}), for the Settings "Edit My Profile" re-entry point to pre-fill its
    pickers. Returns None if the file doesn't exist (onboarding never run, skipped, or the file
    was deleted by hand) -- callers should fall back to the DEFAULT_* constants in that case."""
    path = get_profile_md_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return None

    role = DEFAULT_ROLE
    role_other = ""
    experience = DEFAULT_EXPERIENCE
    style = DEFAULT_STYLE
    for line in content.splitlines():
        m = _ROLE_LINE.match(line)
        if m:
            role = _reverse_lookup(ROLE_CHOICES, m.group(1), DEFAULT_ROLE)
            continue
        m = _ROLE_OTHER_LINE.match(line)
        if m:
            role_other = m.group(1).strip()
            continue
        m = _EXPERIENCE_LINE.match(line)
        if m:
            experience = _reverse_lookup(EXPERIENCE_CHOICES, m.group(1), DEFAULT_EXPERIENCE)
            continue
        m = _STYLE_LINE.match(line)
        if m:
            style = _reverse_lookup(STYLE_CHOICES, m.group(1), DEFAULT_STYLE)
            continue

    return {"role": role, "role_other": role_other, "experience": experience, "style": style}


def get_formatted_onboarding_context():
    """Returns a system-prompt-ready block, or None if no profile has been saved (onboarding
    skipped, or the file was deleted) -- prompts.py's build_system_prompt() already has a
    guarded, optional-block pattern for exactly this shape (see memory_manager/task_manager
    there), so callers need no special-casing beyond checking for None.

    Built fresh from the parsed values rather than dumping the raw .md file verbatim: the file
    also carries a human-facing "how to edit this" sentence that has nothing to do with how the
    model should behave, so re-composing a clean instructional block avoids wasting tokens on
    text meant for a person, not the model."""
    profile = load_onboarding_profile()
    if profile is None:
        return None

    role_label = ROLE_CHOICES.get(profile["role"], ROLE_CHOICES[DEFAULT_ROLE])
    if profile["role"] == "other" and profile["role_other"]:
        role_label = profile["role_other"]
    experience_label = EXPERIENCE_CHOICES.get(profile["experience"], EXPERIENCE_CHOICES[DEFAULT_EXPERIENCE])
    style_label = STYLE_CHOICES.get(profile["style"], STYLE_CHOICES[DEFAULT_STYLE])

    return (
        "## User Profile\n"
        f"- Role: {role_label}\n"
        f"- QGIS experience: {experience_label}\n"
        f"- Preferred communication style: {style_label}\n"
        "Adjust explanations, defaults, and terminology to match this profile -- for example, "
        "explain more for a beginner and less for an expert, and match the requested tone."
    )
