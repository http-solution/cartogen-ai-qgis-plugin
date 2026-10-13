"""
search_fact_checks: "has this claim, video or photo been fact-checked?" against the published feeds of named fact-checking outlets.

Why (owner request 2026-10-13, tracker 1.19): incident and conflict reports on social media are often old footage, edited images or
rumours. The owner named Reuters Fact Check, AFP Fact Check and Full Fact. Checked live on 2026-10-13 from a development session:
Reuters answers 401 and AFP 403 to a program, so they cannot be read; Full Fact now publishes a feed (the earlier 404 was a wrong address);
Snopes, PolitiFact, FactCheck.org, Lead Stories and the Arabic-language Fatabyyano (whose recent items include Yemen and Syria footage) do too.

What this is NOT: a search of every fact-check ever published. A feed holds only an outlet's newest 10-25 entries, so the tool can say "these
outlets recently published this" and can never say "nobody has checked this". Every reply carries that sentence, and lists the outlets that
answered, the ones that failed and the ones that cannot be asked. The text of a fact-check is the outlet's own words and is returned as
data, never as instructions.

Pure network phase (no QGIS object touched); runs on the worker thread like the other network-only tools. The feeds were verified live from a
development session; not verified inside a running QGIS session.
"""
import contextlib
import html
import re
import xml.etree.ElementTree as ElementTree
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from .registry import register_tool
from ._urllib_retry import urlopen_with_retry
from ...net import build_request as _net_build_request
from ...net import read_capped as _read_capped

# id -> the outlet. `skip_categories`: feed entries in these categories are the outlet's own announcements, not fact-checks.
FEEDS = {
    "snopes": {"name": "Snopes", "url": "https://www.snopes.com/feed/", "language": "en", "coverage": "global, mostly US-origin claims"},
    "politifact": {"name": "PolitiFact", "url": "https://www.politifact.com/rss/factchecks/", "language": "en", "coverage": "US politics"},
    "factcheck_org": {"name": "FactCheck.org", "url": "https://www.factcheck.org/feed/", "language": "en", "coverage": "US politics"},
    "full_fact": {"name": "Full Fact", "url": "https://fullfact.org/feed/all/", "language": "en", "coverage": "UK, some international"},
    "lead_stories": {"name": "Lead Stories", "url": "https://leadstories.com/atom.xml", "language": "en", "coverage": "global online rumours"},
    "fatabyyano": {"name": "Fatabyyano (فتبينوا)", "url": "https://fatabyyano.net/feed/", "language": "ar", "coverage": "Arabic-language claims, Middle East and North Africa",
                   "skip_categories": ("أخبار منصة فتبينوا",)},
}

# Outlets the owner named (or that a user would expect) and why they are not asked. Shown in every reply.
NOT_SEARCHED = {
    "Reuters Fact Check": "answers an automated request with HTTP 401 (login wall)",
    "AFP Fact Check": "refuses automated requests (HTTP 403)",
    "Africa Check": "refuses automated requests (HTTP 403)",
    "AP Fact Check": "refuses automated requests (HTTP 403)",
}

COVERAGE_NOTE = (
    "This searches only the newest entries (usually 10 to 25) of each outlet's published feed, not the outlets' archives and not the whole web. "
    "A match means one of these outlets recently published a check that mentions your words. NO match does NOT mean the claim is true, false "
    "or unchecked: it only means it is not in these feeds' recent entries. The ratings and conclusions are the outlets' own; read the linked "
    "article before relying on them."
)

DEFAULT_SOURCES = tuple(FEEDS)
MAX_RESULTS = 50
_MAX_FEED_CHARS = 3_000_000
_SUMMARY_CHARS = 280
_STOPWORDS = frozenset({
    "the", "a", "an", "of", "in", "on", "at", "to", "and", "or", "is", "are", "was", "were", "this", "that", "video", "photo", "image",
    "claim", "claims", "fact", "check", "about", "from", "with", "for", "by", "has", "have", "been", "it", "its", "as", "be",
})
_ATOM = "{http://www.w3.org/2005/Atom}"


def _text(el):
    return (el.text or "").strip() if el is not None else ""


def _clean(value, limit=_SUMMARY_CHARS):
    """Third-party markup reduced to short plain text: tags removed, entities decoded, whitespace collapsed, length capped."""
    text = re.sub(r"<[^>]+>", " ", html.unescape(str(value or "")))
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return text[:limit]


def _date10(value):
    value = str(value or "").strip()
    m = re.match(r"(\d{4}-\d{2}-\d{2})", value)
    if m:
        return m.group(1)
    with contextlib.suppress(Exception):
        return parsedate_to_datetime(value).strftime("%Y-%m-%d")
    return ""


_KNOWN_PREFIXES = {
    "content": "http://purl.org/rss/1.0/modules/content/", "dc": "http://purl.org/dc/elements/1.1/",
    "media": "http://search.yahoo.com/mrss/", "atom": "http://www.w3.org/2005/Atom", "wfw": "http://wellformedweb.org/CommentAPI/",
    "slash": "http://purl.org/rss/1.0/modules/slash/", "sy": "http://purl.org/rss/1.0/modules/syndication/",
}


def _declare_missing_prefixes(xml_text):
    """Adds a namespace declaration to the root tag for every prefix a feed uses in an element name without declaring. PolitiFact's feed uses
    `content:encoded` and `snf:analytics` with no declarations, which a strict XML parser rejects ("unbound prefix"); browsers and feed
    readers forgive it. Well-known prefixes get their real namespace, any other a placeholder (this tool reads only title, link, date,
    description and summary, never an element in a made-up namespace)."""
    m = re.search(r"<rss\b[^>]*>|<feed\b[^>]*>", xml_text)
    if not m:
        return xml_text
    root_tag = m.group(0)
    used = dict.fromkeys(re.findall(r"</?([A-Za-z_][\w.-]*):[A-Za-z_]", xml_text))
    extra = "".join(f' xmlns:{p}="{_KNOWN_PREFIXES.get(p, "urn:undeclared:" + p)}"' for p in used
                    if p != "xml" and f"xmlns:{p}=" not in root_tag)
    if not extra:
        return xml_text
    return xml_text[:m.start()] + root_tag[:-1].rstrip("/") + extra + root_tag[-1] + xml_text[m.end():]


def parse_feed(xml_text, source):
    """Pure: an RSS 2.0 or Atom document -> [{source, source_name, title, url, date, summary, language}] for outlet `source` (a FEEDS key).
    A document that is too large or declares entities (the "billion laughs" attack: a feed has no reason to declare any) is refused."""
    xml_text = xml_text.lstrip("\ufeff \t\r\n")        # PolitiFact's feed starts with blank lines, which the XML parser rejects (found live 2026-10-13)
    if len(xml_text) > _MAX_FEED_CHARS or "<!doctype" in xml_text.lower() or "<!entity" in xml_text.lower():
        raise ValueError("the feed was too large or declared entities, so it was not parsed")
    xml_text = _declare_missing_prefixes(xml_text)
    meta = FEEDS[source]
    skip = tuple(meta.get("skip_categories", ()))
    root = ElementTree.fromstring(xml_text)  # noqa: S314 (DOCTYPE / ENTITY refused and size capped above)
    out = []
    for item in root.iter("item"):
        if any(_text(c) in skip for c in item.findall("category")):
            continue
        out.append(_entry(source, meta, _text(item.find("title")), _text(item.find("link")), _text(item.find("pubDate")),
                          item.findtext("description") or ""))
    for entry in root.iter(f"{_ATOM}entry"):
        link = ""
        for ln in entry.findall(f"{_ATOM}link"):
            if ln.get("rel", "alternate") == "alternate" and ln.get("href"):
                link = ln.get("href")
                break
        out.append(_entry(source, meta, _text(entry.find(f"{_ATOM}title")), link,
                          _text(entry.find(f"{_ATOM}published")) or _text(entry.find(f"{_ATOM}updated")),
                          entry.findtext(f"{_ATOM}summary") or ""))
    return [e for e in out if e["title"] and e["url"].startswith(("http://", "https://"))]


def _entry(source, meta, title, url, date, summary):
    return {"source": source, "source_name": meta["name"], "title": _clean(title, 300), "url": url.strip(), "date": _date10(date),
            "summary": _clean(summary), "language": meta["language"]}


def _terms(query):
    words = re.findall(r"[^\W_]+", str(query or "").lower())
    return [w for w in dict.fromkeys(words) if w not in _STOPWORDS and (len(w) > 2 or not w.isascii())]


def match_entries(entries, query, since=None):
    """Pure: entries that mention at least half of the query's meaningful words (all of them rank first), newest first within a score;
    only those on or after `since` ('YYYY-MM-DD'). Returns [(entry with matched_terms and match), ...]."""
    terms = _terms(query)
    if not terms:
        return []
    need = max(1, (len(terms) + 1) // 2)
    scored = []
    for e in entries:
        if since and e["date"] and e["date"] < since:
            continue
        hay = f"{e['title']} {e['summary']}".lower()
        hit = [t for t in terms if t in hay]
        if len(hit) >= need:
            scored.append(dict(e, matched_terms=hit, match="all words" if len(hit) == len(terms) else "some words"))
    scored.sort(key=lambda e: (len(e["matched_terms"]), e["date"]), reverse=True)
    return scored


def source_table():
    return [{"id": k, "name": v["name"], "language": v["language"], "coverage": v["coverage"]} for k, v in FEEDS.items()]


def _fetch(source):
    """(entries, None) or (None, reason) for one outlet. Never raises."""
    try:
        req = _net_build_request(FEEDS[source]["url"], headers={"User-Agent": "Mozilla/5.0 QGIS-AI-Assistant"})
        with urlopen_with_retry(req, timeout=45) as response:
            text = _read_capped(response).decode("utf-8", errors="replace")
        return parse_feed(text, source), None
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:160]}"


def search_fact_checks_network_phase(query, days=60, max_results=15, sources=None):
    """Asks each chosen outlet's feed in parallel and returns matching fact-checks. No QGIS access."""
    if not _terms(query):
        return {"error": "query needs at least one meaningful word (a place, event, person or phrase from the claim)."}
    chosen = [s for s in (sources or DEFAULT_SOURCES) if s in FEEDS]
    unknown = [s for s in (sources or []) if s not in FEEDS]
    if not chosen:
        return {"error": f"No known outlet in sources {sources}. Available: {list(FEEDS)}"}
    try:
        days = min(max(int(days), 1), 3650)
        max_results = min(max(int(max_results), 1), MAX_RESULTS)
    except (TypeError, ValueError):
        return {"error": "days and max_results must be whole numbers."}
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    answered, failed, entries = [], {}, []
    with ThreadPoolExecutor(max_workers=len(chosen)) as pool:
        futures = {s: pool.submit(_fetch, s) for s in chosen}
        for s, fut in futures.items():
            got, reason = fut.result()
            if got is None:
                failed[s] = reason
            else:
                answered.append(s)
                entries += got
    matches = match_entries(entries, query, since)
    return {
        "success": True,
        "query": str(query)[:200],
        "since": since,
        "results": [{k: m[k] for k in ("source_name", "title", "url", "date", "summary", "language", "match", "matched_terms")}
                    for m in matches[:max_results]],
        "match_count": len(matches),
        "entries_searched": len(entries),
        "sources_answered": [FEEDS[s]["name"] for s in answered],
        "sources_failed": {FEEDS[s]["name"]: r for s, r in failed.items()},
        "sources_not_searched": dict(NOT_SEARCHED),
        **({"unknown_sources_ignored": unknown} if unknown else {}),
        "coverage_note": COVERAGE_NOTE,
    }


@register_tool(
    "search_fact_checks",
    "Look up whether a CLAIM, VIDEO, PHOTO or RUMOUR has recently been fact-checked, in the published feeds of named fact-checking outlets "
    "(Snopes, PolitiFact, FactCheck.org, Full Fact, Lead Stories and the Arabic-language Fatabyyano). Use it when the user asks 'is this true', "
    "'was this video really from <place>', 'has this been debunked' or wants to verify a social-media report before mapping it. Give the "
    "distinctive words of the claim (place, event, person), not a whole sentence. Returns each matching check with the outlet, date, link and a "
    "short summary, and ALWAYS says which outlets answered or failed and that this covers only each outlet's newest entries: no match is NOT "
    "evidence that a claim is true, false or unchecked, so never say that. Reuters, AFP, Africa Check and AP cannot be asked (they refuse "
    "automated requests). Quote the outlet's conclusion as theirs and give the link; do not add your own verdict.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Distinctive words of the claim, e.g. 'Hodeidah port strike video' or 'Taiz protest'."},
            "days": {"type": "integer", "description": "Only checks published in the last N days (default 60)."},
            "max_results": {"type": "integer", "description": f"Most matches to return, 1-{MAX_RESULTS} (default 15)."},
            "sources": {"type": "array", "items": {"type": "string"}, "description": f"Optional subset of {list(FEEDS)}; default all."},
        },
        "required": ["query"],
    },
)
def search_fact_checks(query, days=60, max_results=15, sources=None):
    return search_fact_checks_network_phase(query, days, max_results, sources)
