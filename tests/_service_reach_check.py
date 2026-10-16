"""Package J: which of the showcase services (S1 Copernicus DEM, S3 web research, S4 news) can be reached from CI, measured instead of
assumed. Run as `python -m tests._service_reach_check` (no QGIS needed): it calls each service with the plugin's own request helper and
parsers, prints a table, and appends it to $GITHUB_STEP_SUMMARY when set. It always exits 0 -- a service that rate-limits or blocks the CI
runner is a recorded result, not a build failure, and nothing here is mocked into a pass.

Status words:
  reached            the service answered and the plugin's parser found content
  reached, empty     it answered with a valid but empty result
  unavailable        it answered with something that is not results (rate limit, captcha, block page)
  unreachable        the request itself failed (DNS, TLS, timeout, HTTP error)"""
import os
import sys
import urllib.error
import urllib.parse

REACHED, EMPTY, UNAVAILABLE, UNREACHABLE = "reached", "reached, empty", "unavailable", "unreachable"


def classify(name, fn):
    """Runs fn() -> number of items found, and returns {service, status, detail}. Never raises."""
    from cartogen_ai.core.agent.tools.web_research_tools import SearchUnavailableError
    try:
        count = fn()
    except SearchUnavailableError as e:
        return {"service": name, "status": UNAVAILABLE, "detail": str(e)[:160]}
    except urllib.error.HTTPError as e:
        # the service answered: 429 / 403 / 503 are its rate limit or block, which is "unavailable", not "unreachable"
        if e.code in (403, 429, 503):
            return {"service": name, "status": UNAVAILABLE, "detail": f"HTTP {e.code} {str(e.reason)[:100]} (rate limit or block)"}
        return {"service": name, "status": UNREACHABLE, "detail": f"HTTP {e.code} {str(e.reason)[:100]}"}
    except Exception as e:
        return {"service": name, "status": UNREACHABLE, "detail": f"{type(e).__name__}: {str(e)[:140]}"}
    return {"service": name, "status": REACHED if count else EMPTY, "detail": f"{count} item(s)"}


def _gdelt():
    from cartogen_ai.core.agent.tools import web_research_tools as w
    params = urllib.parse.urlencode({"query": "Yemen", "mode": "artlist", "maxrecords": 5, "format": "json", "sort": "datedesc", "timespan": "7d"})
    return len(w.parse_gdelt_articles(w._get_text(f"{w.GDELT_DOC}?{params}")))


def _google_news():
    from cartogen_ai.core.agent.tools import web_research_tools as w
    query = urllib.parse.urlencode({"q": "Yemen when:7d", "hl": "en", "gl": "US", "ceid": "US:en"})
    return len(w.parse_news_rss(w._get_text(f"{w.GOOGLE_NEWS_RSS}?{query}")))


def _duckduckgo():
    from cartogen_ai.core.agent.tools import web_research_tools as w
    return len(w.parse_ddg_html(w._get_text(f"{w.DDG_HTML}?{urllib.parse.urlencode({'q': 'Yemen humanitarian situation'})}")))


def _copernicus_dem():
    """One Range request for the first KB of the tile over Yemen, checked for a TIFF header. No GDAL needed to answer 'is it reachable'."""
    import urllib.request
    from cartogen_ai.core.agent.tools import dem_tools
    request = urllib.request.Request(dem_tools.tile_url(15, 44), headers={"Range": "bytes=0-1023", "User-Agent": "CartogenAI-QGIS reach check"})
    with urllib.request.urlopen(request, timeout=30) as response:
        head = response.read(1024)
    if head[:4] not in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"):
        raise ValueError("the tile answered but does not start like a TIFF")
    return 1


CHECKS = (("S1 Copernicus DEM tile (S3 bucket, Range read)", _copernicus_dem), ("S3 DuckDuckGo web page", _duckduckgo),
          ("S4 GDELT DOC API", _gdelt), ("S4 Google News RSS", _google_news))


def render(results):
    lines = ["| Service | Result | Detail |", "|---|---|---|"]
    lines += [f"| {r['service'].replace('|', '/')} | {r['status']} | {r['detail'].replace('|', '/')} |" for r in results]
    return "\n".join(lines)


def main(checks=CHECKS):
    results = [classify(name, fn) for name, fn in checks]
    table = render(results)
    print(table)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("### Showcase services reached from CI\n\n" + table + "\n")
    return results


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
    main()
