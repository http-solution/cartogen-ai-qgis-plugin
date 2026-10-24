"""PLAN-014 phase 2b: map product profiles, a small JSON file an organisation writes once and names in create_print_layout(profile=...).

Why a file and not built-in templates: the plugin does not carry any organisation's template rules, logo or brand colours (owner decision,
2026-10-24: the organisation supplies its own, like its disclaimer wording). A profile holds the choices a team repeats on every map: page size
and orientation, the export purpose, the exported file name, and which layout elements its products must have. Branding fields: logo, masthead colours and
font (phase 3a); sign-off and the COD flag are later phases. An unknown field is REFUSED with its name, never silently ignored, so a file written for a
later version cannot look as if it worked.

Looked up in the project folder (`cartogen_profiles/<name>.json`) first, then in the QGIS profile folder (`cartogen_ai/profiles/<name>.json`).
Validation and lookup are pure/offline; only the two folder locations need QGIS and fall back to nothing outside it."""
import json
import os
import re

from .layout_options import EXPORT_PRESETS, export_file_name  # noqa: F401  (export_file_name re-exported for callers building a name)
from .layout_page_scale import PAGE_SIZE_KEYS

PROFILE_VERSION = 1
KNOWN_ELEMENTS = ("MAP_MAIN", "TITLE", "LEGEND", "SCALEBAR", "NORTH_ARROW", "MAP_INFO", "FOOTER", "BODY_TEXT", "INSET_MAP")
PLACEHOLDERS = ("title", "date", "layout")
FIELDS = ("profile_version", "name", "description", "page_size", "orientation", "export_preset", "file_name_pattern", "required_elements",
          "logo_path", "logo_position", "masthead_colour", "masthead_text_colour", "font_family",
          "footer_lines", "sign_off", "require_sign_off")
SIGN_OFF_KEYS = ("prepared_by", "reviewed_by", "review_date", "status")
SIGN_OFF_STATUSES = ("Draft", "Reviewed", "Approved")
MAX_FOOTER_LINES = 3
MAX_FOOTER_LINE_CHARS = 120
LOGO_EXTENSIONS = (".png", ".jpg", ".jpeg")   # not SVG: an SVG can reference files and URLs outside itself (owner decision 2026-10-24)
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_FONT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,63}$")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\- ]{0,63}$")
_PATTERN_FIELD = re.compile(r"\{([^{}]*)\}")
MAX_FILE_BYTES = 20_000


def example_profile():
    """A generic profile that shows every field. It carries no organisation's name, mark or wording. Pure."""
    return {
        "profile_version": PROFILE_VERSION,
        "name": "example-situation-map",
        "description": "Example only: A3 landscape, print resolution, dated file names, five mandatory elements.",
        "page_size": "A3",
        "orientation": "landscape",
        "export_preset": "print",
        "file_name_pattern": "{title}_{date}",
        "required_elements": ["MAP_MAIN", "TITLE", "LEGEND", "SCALEBAR", "NORTH_ARROW"],
        "masthead_colour": "#2b5d8a",
        "masthead_text_colour": "#ffffff",
    }


def validate_profile(data):
    """(clean profile dict, []) or (None, [problem, ...]) for a parsed JSON profile. Every problem is listed at once. Pure."""
    if not isinstance(data, dict):
        return None, ["the profile must be a JSON object ({ ... })"]
    problems = [f"unknown field '{key}' (known fields: {', '.join(FIELDS)})"
                for key in data if key not in FIELDS]
    version = data.get("profile_version", PROFILE_VERSION)
    if version != PROFILE_VERSION:
        problems.append(f"profile_version must be {PROFILE_VERSION}")
    clean = {"profile_version": PROFILE_VERSION}
    name = data.get("name")
    if name is not None:
        if not isinstance(name, str) or not _NAME.match(name):
            problems.append("name must be 1 to 64 letters, digits, spaces, '-' or '_'")
        else:
            clean["name"] = name
    description = data.get("description")
    if description is not None:
        if not isinstance(description, str) or len(description) > 300:
            problems.append("description must be text of at most 300 characters")
        else:
            clean["description"] = description
    size = data.get("page_size")
    if size is not None:
        key = str(size).strip().lower().replace(" ", "")
        if key not in PAGE_SIZE_KEYS:
            problems.append(f"page_size must be one of {', '.join(k.upper() for k in PAGE_SIZE_KEYS)}")
        else:
            clean["page_size"] = key.upper()
    orientation = data.get("orientation")
    if orientation is not None:
        if str(orientation).strip().lower() not in ("landscape", "portrait"):
            problems.append("orientation must be 'landscape' or 'portrait'")
        else:
            clean["orientation"] = str(orientation).strip().capitalize()
    preset = data.get("export_preset")
    if preset is not None:
        if str(preset).strip().lower() not in EXPORT_PRESETS:
            problems.append(f"export_preset must be one of {', '.join(EXPORT_PRESETS)}")
        else:
            clean["export_preset"] = str(preset).strip().lower()
    pattern = data.get("file_name_pattern")
    if pattern is not None:
        bad = [f for f in _PATTERN_FIELD.findall(str(pattern)) if f not in PLACEHOLDERS]
        stripped = _PATTERN_FIELD.sub("", str(pattern))
        if not isinstance(pattern, str) or not pattern.strip() or len(pattern) > 100 or bad or "{" in stripped or "}" in stripped:
            problems.append(f"file_name_pattern must be 1 to 100 characters using only {', '.join('{' + p + '}' for p in PLACEHOLDERS)}")
        else:
            clean["file_name_pattern"] = pattern
    elements = data.get("required_elements")
    if elements is not None:
        if not isinstance(elements, list) or not elements or any(e not in KNOWN_ELEMENTS for e in elements):
            problems.append(f"required_elements must be a non-empty list of: {', '.join(KNOWN_ELEMENTS)}")
        else:
            clean["required_elements"] = list(dict.fromkeys(elements))
    _validate_branding(data, clean, problems)
    _validate_footer_fields(data, clean, problems)
    return (None, problems) if problems else (clean, [])


def logo_path_problem(path):
    """Why `path` cannot be a logo (a URL, a network path, a parent-folder step, or not PNG/JPG), else None. Pure."""
    text = str(path or "").strip()
    if not text or len(text) > 260:
        return "logo_path must be a file path of at most 260 characters"
    if re.match(r"^[A-Za-z][A-Za-z0-9+.\-]*://", text) or text.startswith(("\\\\", "//")):
        return "logo_path must be a local file (web addresses and network paths are refused)"
    if ".." in re.split(r"[\\/]", text):
        return "logo_path must not contain '..'"
    if not text.lower().endswith(LOGO_EXTENSIONS):
        return "logo_path must be a PNG or JPG file"
    return None


def _validate_branding(data, clean, problems):
    """Phase 3a fields: logo, masthead colours, font. Each problem is added by name. Pure."""
    if "logo_path" in data:
        problem = logo_path_problem(data["logo_path"])
        if problem:
            problems.append(problem)
        else:
            clean["logo_path"] = str(data["logo_path"]).strip()
    if "logo_position" in data:
        if str(data["logo_position"]).strip().lower() not in ("left", "right"):
            problems.append("logo_position must be 'left' or 'right'")
        else:
            clean["logo_position"] = str(data["logo_position"]).strip().lower()
    for key in ("masthead_colour", "masthead_text_colour"):
        if key in data:
            if not isinstance(data[key], str) or not _HEX.match(data[key].strip()):
                problems.append(f"{key} must be a hex colour like #1f2d3a")
            else:
                clean[key] = data[key].strip().lower()
    if "font_family" in data:
        if not isinstance(data["font_family"], str) or not _FONT.match(data["font_family"].strip()):
            problems.append("font_family must be a font name of at most 64 letters, digits, spaces, '.', '-' or '_'")
        else:
            clean["font_family"] = data["font_family"].strip()


def _validate_footer_fields(data, clean, problems):
    """Phase 3b fields: extra footer lines, the reviewer sign-off and the switch that makes it mandatory for publication. Pure."""
    lines = data.get("footer_lines")
    if "footer_lines" in data:
        ok = (isinstance(lines, list) and 1 <= len(lines) <= MAX_FOOTER_LINES
              and all(isinstance(x, str) and x.strip() and len(x) <= MAX_FOOTER_LINE_CHARS and "\n" not in x for x in lines))
        if ok:
            clean["footer_lines"] = [x.strip() for x in lines]
        else:
            problems.append(f"footer_lines must be 1 to {MAX_FOOTER_LINES} single-line texts of at most {MAX_FOOTER_LINE_CHARS} characters")
    if "sign_off" in data:
        value, issues = validate_sign_off(data["sign_off"])
        problems.extend(issues)
        if value is not None:
            clean["sign_off"] = value
    if "require_sign_off" in data:
        if not isinstance(data["require_sign_off"], bool):
            problems.append("require_sign_off must be true or false")
        else:
            clean["require_sign_off"] = data["require_sign_off"]


def validate_sign_off(data):
    """(clean sign-off dict, []) or (None, [problem, ...]). 'Reviewed' and 'Approved' need a reviewer name and a real date: a status
    cannot claim a review nobody is named for. Pure."""
    import datetime
    if not isinstance(data, dict) or not data:
        return None, ["sign_off must be an object with prepared_by, reviewed_by, review_date and/or status"]
    problems = [f"sign_off: unknown key '{k}' (known: {', '.join(SIGN_OFF_KEYS)})" for k in data if k not in SIGN_OFF_KEYS]
    clean = {}
    for key in ("prepared_by", "reviewed_by"):
        if key in data:
            if not isinstance(data[key], str) or not data[key].strip() or len(data[key]) > 80 or "\n" in data[key]:
                problems.append(f"sign_off.{key} must be a name of at most 80 characters")
            else:
                clean[key] = data[key].strip()
    if "review_date" in data:
        try:
            clean["review_date"] = datetime.date.fromisoformat(str(data["review_date"])).isoformat()
        except ValueError:
            problems.append("sign_off.review_date must be a real date written YYYY-MM-DD")
    if "status" in data:
        match = [x for x in SIGN_OFF_STATUSES if x.lower() == str(data["status"]).strip().lower()]
        if match:
            clean["status"] = match[0]
        else:
            problems.append(f"sign_off.status must be one of {', '.join(SIGN_OFF_STATUSES)}")
    if clean.get("status") in ("Reviewed", "Approved") and not (clean.get("reviewed_by") and clean.get("review_date")):
        problems.append(f"sign_off.status '{clean['status']}' needs reviewed_by and review_date")
    return (None, problems) if problems else (clean, [])


def sign_off_line(sign_off):
    """The footer line for a sign-off, or ''. Without a named reviewer the status always reads 'Draft - not reviewed'. Pure."""
    if not sign_off:
        return ""
    parts = []
    if sign_off.get("prepared_by"):
        parts.append(f"Prepared by {sign_off['prepared_by']}")
    reviewer = sign_off.get("reviewed_by")
    if reviewer:
        parts.append(f"Reviewed by {reviewer}" + (f" on {sign_off['review_date']}" if sign_off.get("review_date") else ""))
        parts.append(f"Status: {sign_off.get('status') or 'Draft'}")
    else:
        parts.append("Status: Draft - not reviewed")
    return " | ".join(parts)


def sign_off_missing(profile):
    """True when the profile makes sign-off mandatory and it does not show a named, dated review with a Reviewed/Approved status. Pure."""
    if not (profile or {}).get("require_sign_off"):
        return False
    so = profile.get("sign_off") or {}
    return not (so.get("reviewed_by") and so.get("review_date") and so.get("status") in ("Reviewed", "Approved"))


def parse_profile_text(text):
    """validate_profile() of JSON text; a size cap and a syntax error are reported the same way as a field problem. Pure."""
    if len(text.encode("utf-8", "ignore")) > MAX_FILE_BYTES:
        return None, [f"the file is larger than {MAX_FILE_BYTES} bytes"]
    try:
        data = json.loads(text)
    except ValueError as exc:
        return None, [f"not valid JSON ({exc})"]
    return validate_profile(data)


def safe_profile_name(name):
    """The name if it is a plain profile name (no path), else None. Pure."""
    text = str(name or "").strip()
    return text if _NAME.match(text) else None


def profile_dirs():
    """Folders searched for profile files, project folder first. Needs QGIS for the folders; [] without it."""
    out = []
    try:
        from qgis.core import QgsApplication, QgsProject
        home = QgsProject.instance().homePath()
        if home:
            out.append(os.path.join(home, "cartogen_profiles"))
        out.append(os.path.join(QgsApplication.qgisSettingsDirPath(), "cartogen_ai", "profiles"))
    except Exception:
        return []
    return out


def available_profiles(dirs):
    """Sorted profile names (file stems) found in `dirs`. Pure apart from listing the folders."""
    names = set()
    for folder in dirs:
        if os.path.isdir(folder):
            names.update(os.path.splitext(f)[0] for f in os.listdir(folder) if f.lower().endswith(".json"))
    return sorted(names)


def load_profile(name, dirs=None):
    """(profile dict, None) or (None, message) for a profile named `name`. The message says what is wrong or which profiles exist."""
    safe = safe_profile_name(name)
    if safe is None:
        return None, f"'{name}' is not a profile name: use letters, digits, spaces, '-' or '_' only (no folders)."
    folders = profile_dirs() if dirs is None else dirs
    for folder in folders:
        path = os.path.join(folder, safe + ".json")
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as handle:
                    profile, problems = parse_profile_text(handle.read())
            except OSError as exc:
                return None, f"profile '{safe}' could not be read ({exc.__class__.__name__})."
            if problems:
                return None, f"profile '{safe}' ({path}) is not valid: " + "; ".join(problems) + "."
            if profile.get("logo_path") and not os.path.isabs(profile["logo_path"]):
                profile["logo_path"] = os.path.normpath(os.path.join(folder, profile["logo_path"]))   # relative to the profile's own folder
            return profile, None
    found = available_profiles(folders)
    where = " or ".join(folders) if folders else "the project folder (cartogen_profiles) or the QGIS profile folder (cartogen_ai/profiles)"
    return None, (f"No profile named '{safe}' in {where}." + (f" Available: {', '.join(found)}." if found else " None have been saved yet."))
