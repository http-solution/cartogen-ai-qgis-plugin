# PLAN-019: publish the documentation to the GitHub wiki instead of GitHub Pages

Status: in progress

## Goal
The owner chose the wiki over GitHub Pages (2026-10-25). The documentation keeps one source (the repository) and is published to https://github.com/http-solution/cartogen-ai-qgis-plugin/wiki automatically, with no hand-maintained copy.

## Scope
In: `site/build_wiki.py` (the same page model as the HTML site, written as GitHub-wiki Markdown: `Home`, `_Sidebar`, `_Footer`, one page per document, links rewritten, repository images as raw URLs); `site/wiki-home.md` (a plain-Markdown home, because the wiki strips the HTML home page's styling); the `docs-site` workflow changed to check both outputs on pull requests and, on `main`, push the wiki; tests; the README row and `site/content/development/site.md`.
Out: any edit to the wiki through the browser (overwritten by design); deleting `site/build.py` (kept as a second link check; can be retired later); unpublishing the old Pages site (the owner does that in Settings).

Owner decisions (2026-10-25): retire the Pages deploy and keep the link check; generate the wiki from the repository docs and sync it by workflow.

## Facts found before building
- `has_wiki` is true but the wiki's git repository is not readable: GitHub creates it only when the first page is saved in the browser. So the sync job cannot run until the owner saves one page; until then it ends with a warning, not a failure.
- This session cannot push to the wiki (its access is the main repository; the wiki has no API). Only the workflow's built-in token can, after that first page exists.
- The docs are already Markdown (83 files in `docs/` plus `site/content`); the page model in `site/build.py` was split into `assemble()` and `markdown_sources()` so both outputs share it. The HTML build output is unchanged.

## Acceptance
1. `python site/build_wiki.py --check` writes one page per document plus Home, sidebar and footer, and reports no link to an unknown page or missing repository file; `tests/test_wiki_build.py` and `tests/test_site_build.py` pass.
2. The workflow has no Pages deploy (no deploy-pages, no upload-pages-artifact, no `pages: write`); only the sync job has `contents: write` and it does not run on pull requests.
3. After the owner saves the first wiki page and the workflow runs on `main`, the wiki shows the documentation. Not verifiable from here; the owner looks at the wiki.

## Guard tests
`tests/test_wiki_build.py`, `tests/test_site_build.py`.

## Rollback
Revert the pull request: the old Pages workflow returns. The wiki, once pushed, keeps its last content until overwritten.

## Status log
- 2026-10-25: owner asked for the wiki instead of Pages and chose the two options above. Built and tested offline (53 pages, no link errors); the push to the wiki has not been run.
