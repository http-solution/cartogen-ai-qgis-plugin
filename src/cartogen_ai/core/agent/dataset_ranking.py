"""Ranking of data-set search results (PLAN-046, roadmap step E, first slice): a person choosing between five HDX data sets needs to see which is
open, current and about the right place, not only which one the search engine listed first.

Pure. Input is one CKAN package (a dict as HDX returns it); every field may be missing and a missing field is reported as unknown, never guessed.
The score is a plain sum of three parts, each with a stated reason, so the order can be explained and disputed:
  licence   0..40   an open licence scores high; no licence stated scores 0 and says so; a stated non-open licence scores low
  freshness 0..40   by months since the data set was last changed (metadata_modified; a data set updated "never" or "live" is noted, not scored)
  coverage  0..20   10 when the asked-for country is a listed group; 10 for a spatial file, 5 for a table only (needs a join); sub-national detail is
                    reported, not scored (the record cannot say which place)
It ranks what a search returned. It does not check that the file opens, that the licence text is what the owner says, or that the data is correct."""
import re
from datetime import date

OPEN_LICENCE_MARKERS = ("cc-by", "cc by", "cc0", "creative commons attribution", "odc", "public domain", "open data commons", "cc-zero")
UNKNOWN_LICENCE_MARKERS = ("not specified", "unspecified", "")
SPATIAL_FORMATS = ("geojson", "gpkg", "shp", "zip", "kml", "geotiff", "tif")
TABLE_FORMATS = ("csv", "xlsx", "xls")
FRESH_MONTHS = (12, 36, 72)          # up to a year: full marks; to 3 years: half; to 6 years: a quarter; older: none


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def parse_date(value):
    """A datetime.date from an ISO-like string, else None. Pure."""
    match = re.match(r"\s*(\d{4})-(\d{2})-(\d{2})", value) if isinstance(value, str) else None
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def months_between(then, today):
    return max(0, (today.year - then.year) * 12 + (today.month - then.month))


def licence_part(item):
    """(points, label, reason). Pure."""
    label = _text(item.get("license_title")) or _text(item.get("license_id"))
    low = label.lower()
    if low in UNKNOWN_LICENCE_MARKERS or "not specified" in low:
        return 0, label or None, "no licence stated: ask the data owner before publishing a map made from it"
    if "not open" in low:
        return 0, label, f"licence '{label}' is stated as NOT open: do not redistribute or publish without the owner's permission"
    if any(marker in low for marker in OPEN_LICENCE_MARKERS):
        return 40, label, f"open licence ({label})"
    return 10, label, f"licence '{label}' is not recognised as open: read its terms before use"


def freshness_part(item, today):
    """(points, months or None, reason). Pure."""
    freq = _text(item.get("data_update_frequency"))
    changed = parse_date(item.get("metadata_modified")) or parse_date(item.get("last_modified"))
    if changed is None:
        return 0, None, "last change date unknown"
    months = months_between(changed, today)
    if months <= FRESH_MONTHS[0]:
        points = 40
    elif months <= FRESH_MONTHS[1]:
        points = 20
    elif months <= FRESH_MONTHS[2]:
        points = 10
    else:
        points = 0
    note = f"changed {months} month{'s' if months != 1 else ''} ago"
    if freq == "-1":
        note += " (the publisher says it is never updated)"
    return points, months, note


def country_names(item):
    """Lower-case group names and display names. Pure."""
    names = []
    for group in item.get("groups") or []:
        if isinstance(group, dict):
            for key in ("name", "display_name", "title"):
                value = _text(group.get(key)).lower()
                if value and value not in names:
                    names.append(value)
    return names


def coverage_part(item, country=None):
    """(points, reason). `country` is an ISO3 code or a name. Pure."""
    points, bits = 0, []
    wanted = _text(country).lower()
    names = country_names(item)
    if wanted:
        if wanted in names or any(wanted == n or (len(wanted) > 3 and wanted in n) for n in names):
            points += 10
            bits.append(f"lists {country}")
        elif names:
            bits.append(f"does not list {country} (lists: {', '.join(names[:4])})")
        else:
            bits.append("no countries listed")
    formats = {_text(r.get("format")).lower() for r in item.get("resources") or [] if isinstance(r, dict)}
    if formats & set(SPATIAL_FORMATS):
        points += 10
        bits.append("has a spatial file")
    elif formats & set(TABLE_FORMATS):
        points += 5
        bits.append("table only (needs a join to a boundary layer)")
    else:
        bits.append("no usable file format listed")
    if item.get("subnational") in (True, 1, "1", "true", "True"):
        bits.append("sub-national detail")
    return points, "; ".join(bits)


def rank_item(item, today, country=None):
    """The ranking fields for one package: score, parts and reasons. Pure."""
    lp, label, lr = licence_part(item)
    fp, months, fr = freshness_part(item, today)
    cp, cr = coverage_part(item, country)
    return {"score": lp + fp + cp, "licence": label, "months_since_change": months, "why": [lr, fr, cr]}


def rank(items, today=None, country=None):
    """`items` sorted best first with a `ranking` block each; ties keep the search engine's order. Pure given `today`."""
    today = today or date.today()
    scored = [(rank_item(it, today, country), position, it) for position, it in enumerate(items)]
    scored.sort(key=lambda s: (-s[0]["score"], s[1]))
    return [{**it, "ranking": r} for r, _p, it in scored]

