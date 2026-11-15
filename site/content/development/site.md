---
description: How this documentation is generated from the repository, how to build it locally, and how it is published to the GitHub wiki.
---
This site is **built from the repository**, so it cannot drift from the code or the living documents. There is no hand-maintained copy.

## Sources of each page

| Kind | Source | Examples |
|---|---|---|
| **Authored** | `site/content/**/*.md` | Install, architecture pages, security overview, privacy, development, status |
| **Mirrored** | A living repository document, rendered on every build | User guide, `SECURITY.md`, `CONTRIBUTING.md`, the changelog, humanitarian catalogue, trackers |
| **Generated** | Computed from the repository | The tool reference (`docs/TOOLS_REFERENCE.md` split into one page per category plus an A-to-Z index), the task register table (`task_register.json`), the humanitarian workflow table (`core/release_notes.py`), the document index |

Mirrored pages carry a note saying which file they mirror; to correct one, edit that file. **Frozen historical documents are never rewritten**: they are listed on [All documents](@project/documents) and the archive index and linked to GitHub.

Numbers such as the version, tool count, task count and test count are filled in from the repository at build time (`{{version}}`, `{{tools}}`, `{{tasks}}`).

## Build locally

```bash
python -m pip install markdown==3.7
python site/build.py --check          # writes site/_site/ and fails on any broken internal link or anchor
python -m http.server -d site/_site   # then open http://localhost:8000
```

`site/_site/` is git-ignored. The only third-party dependency is `markdown`; everything else is the standard library. The theme (`site/theme/`) is hand-written CSS and a small JavaScript file with no dependencies: light and dark themes, a mobile menu, a "On this page" list, and search that works from `file://` as well as on Pages (the index is a plain script file).

## Links in authored pages

Authored pages link explicitly, and an unresolved link **fails the build**:

| Write | Meaning |
|---|---|
| `[text](@architecture/agent-loop)` | Another site page, by slug (the path without `.html`); add `#anchor` as usual |
| `[text](repo:SECURITY.md)` | A repository file: a site page if it is mirrored, otherwise a link to GitHub |
| `![alt](repo:docs/images/dock-panel.png)` | An image copied into the site |

Relative links inside **mirrored** documents are resolved against that document's own folder: to a site page if it is mirrored, to the image if it is one, otherwise to GitHub. A mirrored page whose heading anchors do not match only produces a warning, because those documents are written for GitHub's anchor style.

## Adding a page

1. Create `site/content/<section>/<name>.md` with a front matter block (`description:`, optionally `wide: true`).
2. Add it to `NAV` in `site/build.py`.
3. Run `python site/build.py --check`.

## Where the documentation is published

The documentation is published to the **GitHub wiki**, not to GitHub Pages (owner decision, 2026-10-25). `site/build_wiki.py` turns the same page model into plain Markdown pages: `Home`, a sidebar, a footer and one file per page. `.github/workflows/docs-site.yml` rebuilds them on every merge to `main` and pushes them to the wiki repository, replacing what is there, so **edits made in the browser are overwritten**; correct the source files instead.

```bash
python site/build_wiki.py --check --out _wiki   # writes the wiki pages and fails on a link to an unknown page or a missing repository file
```

In the wiki, `@slug` becomes the page name, a repository image becomes a `raw.githubusercontent.com` link and any other repository file a github.com link. The wiki home page is `site/wiki-home.md` (plain Markdown, because the wiki strips the styling the HTML home page uses).

The HTML build (`python site/build.py --check`) is still run on every pull request as a second link check, but the HTML site is no longer deployed.

One-time owner steps: GitHub creates the wiki's git repository only when the first wiki page is saved in the browser (Wiki tab, Create the first page), and the old Pages site comes down with Settings > Pages > Unpublish site. Until the first page exists the sync job ends with a warning instead of failing.
