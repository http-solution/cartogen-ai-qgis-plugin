# Showcase services: what was measured, and from where (2026-10-16)

The S1 to S4 showcase fixes depend on four outside services. Until now they were labelled "unverified". `tests/_service_reach_check.py` calls each
one with the plugin's own request helper and parsers and records the outcome. A new job, `service-reach` in `.github/workflows/tests.yml`, runs it
on every push and pull request and writes the table into the job summary. The job is informational (`continue-on-error`, exit code always 0): a
rate-limited service is a result, not a failed build, and nothing is mocked into a pass.

## First measurement (from the Claude Code cloud sandbox, not from CI and not from a user's machine)

| Service | Result | Detail |
|---|---|---|
| S1 Copernicus DEM tile (Range read of the first KB, TIFF header checked) | reached | the tile over Yemen answered with a TIFF header |
| S3 DuckDuckGo web page | unavailable | answered, but the page had no result list (blocked, or the layout changed) |
| S4 GDELT DOC API | unavailable | HTTP 429 (rate limit) |
| S4 Google News RSS | reached | 100 items parsed |

What this does and does not show:

* It shows the parsers work on live responses from Google News and that the DEM tile URL is right. It does **not** show a QGIS download of the
  DEM into a project (that needs the live job and GDAL's network reader), and it says nothing about a user's own network.
* GDELT and DuckDuckGo answered with a limit or a block from this sandbox. Whether the CI runner or a user is limited the same way varies with
  the address; the plugin already falls back from GDELT to Google News and reports a service it cannot use (`fetch_news_articles`,
  `fetch_web_results`).
* The authoritative number for the CI runner is the `service-reach` job summary on any pull request.
