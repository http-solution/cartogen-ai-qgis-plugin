#!/usr/bin/env python3
"""Exports the Cartogen AI documentation as GitHub Wiki pages (Markdown), from the same page model as the HTML site (site/build.py).

    python site/build_wiki.py --out _wiki            # writes Home.md, _Sidebar.md, _Footer.md and one <Page-name>.md per page
    python site/build_wiki.py --out _wiki --check    # also exit 1 on a link to an unknown page or a missing repository file

Why: the owner chose the wiki over GitHub Pages (2026-10-25). The wiki is generated, never hand-edited: the docs-site workflow rebuilds it
on every merge to main and pushes it to `<repo>.wiki.git`, replacing what is there. Nothing here needs the `markdown` package at render time
(GitHub renders the Markdown), but the page model and the generated pages (tool reference, task register, workflows) come from site/build.py.

Links: authored pages use `@slug` for a page and `repo:path` for a repository file, as for the HTML site. Here `@slug` becomes the wiki page
name, a repository image becomes a raw.githubusercontent.com URL, any other repository file a github.com blob/tree link. Mirrored repository
documents keep their own relative links, resolved against the file's folder. Code blocks and inline code are never touched."""
import argparse
import importlib.util
import os
import posixpath
import re
import shutil
import subprocess
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent


def _load_site_build():
    spec = importlib.util.spec_from_file_location("cartogen_site_build", SITE / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B = _load_site_build()
REPO, GITHUB, BRANCH, IMAGE_EXTS = B.REPO, B.GITHUB, B.BRANCH, B.IMAGE_EXTS
RAW = "https://raw.githubusercontent.com/http-solution/cartogen-ai-qgis-plugin/" + BRANCH
_EXTERNAL = re.compile(r"^(https?:|mailto:|data:|javascript:|tel:)")
_BAD_NAME_CHARS = re.compile(r'[\\/:*?"<>|#%\[\]{}^~`&()\',;!+=@$]+')


def _clean_name(title):
    """A page title as a wiki file name: '&' becomes 'and', punctuation that breaks a Markdown link ( ) , ' and the like is dropped, spaces and
    runs of hyphens become single hyphens."""
    text = title.replace("&", " and ").replace("%", " percent ")
    text = _BAD_NAME_CHARS.sub(" ", text)
    return re.sub(r"[\s-]+", "-", text).strip("-.")


def page_names(pages):
    """slug -> wiki page name (the file name without .md). 'index' is Home. Names come from the page title, made file-safe; a title that is
    already taken gets its section in front. Deterministic, so a link written today still works after the next sync."""
    names, used = {}, {"Home"}
    for slug, page in pages.items():
        if slug == "index":
            names[slug] = "Home"
            continue
        base = _clean_name(page.title) or slug.replace("/", "-")
        name = base
        if name in used:
            name = _clean_name(f"{page.section} {page.title}")
        n = 2
        while name in used:
            name = f"{base}-{n}"
            n += 1
        used.add(name)
        names[slug] = name
    return names


class WikiLinker:
    def __init__(self, pages, names):
        self.pages = pages
        self.names = names
        self.by_src = {p.spec.get("path"): p for p in pages.values() if p.spec.get("path")}
        self.errors = []
        self.warnings = []

    @staticmethod
    def github(repo_path):
        kind = "tree" if (REPO / repo_path).is_dir() else "blob"
        return f"{GITHUB}/{kind}/{BRANCH}/{repo_path}".rstrip("/")

    def resolve(self, href, page, is_image=False):
        if _EXTERNAL.match(href) or href.startswith("#"):
            return href
        target, frag = href, ""
        if "#" in href:
            target, frag = href.split("#", 1)
            frag = "#" + frag
        if target.startswith("@"):
            slug = target[1:]
            if slug not in self.pages:
                self.errors.append(f"{page.slug}: link to unknown page {href}")
                return href
            return self.names[slug] + frag
        if target.startswith(("repo:", "asset:")):
            return self.repo_target(target.split(":", 1)[1], frag, page, is_image)
        if page.mirror:
            base = posixpath.dirname(page.spec.get("path", ""))
            repo_path = posixpath.normpath(posixpath.join(base, target)) if target else page.spec.get("path", "")
            return self.repo_target(repo_path, frag, page, is_image, lenient=True)
        self.errors.append(f"{page.slug}: relative link {href!r} must use @slug or repo:path")
        return href

    def repo_target(self, repo_path, frag, page, is_image, lenient=False):
        if repo_path in self.by_src:
            return self.names[self.by_src[repo_path].slug] + frag
        if repo_path == "docs/TOOLS_REFERENCE.md":
            return self.names["tools/index"] + frag
        full = REPO / repo_path
        if repo_path.lower().endswith(IMAGE_EXTS):
            if not full.is_file():
                self.errors.append(f"{page.slug}: image {repo_path} not found")
                return repo_path
            return f"{RAW}/{repo_path}"
        if not full.exists():
            (self.warnings if lenient else self.errors).append(f"{page.slug}: {repo_path} does not exist in the repository")
        return self.github(repo_path) + frag

    # ---- Markdown rewriting (outside code only) ----
    _INLINE = re.compile(r'(!?)(\[(?:[^\[\]]|\[[^\]]*\])*\])\(\s*(<[^>]*>|[^)\s]+)((?:\s+"[^"]*")?)\s*\)')
    _REFDEF = re.compile(r"^(\s{0,3}\[[^\]]+\]:\s*)(\S+)(.*)$")
    _HTMLATTR = re.compile(r'\b(href|src)=(["\'])(.*?)\2')
    _CODE_SPAN = re.compile(r"(`+)(?:(?!\1).)+?\1")

    def rewrite(self, text, page):
        out, fence = [], None
        for line in text.split("\n"):
            stripped = line.lstrip()
            if stripped.startswith(("```", "~~~")):
                marker = stripped[:3]
                fence = None if fence == marker else (fence or marker)
                out.append(line)
                continue
            if fence:
                out.append(line)
                continue
            out.append(self._rewrite_line(line, page))
        return "\n".join(out)

    def _rewrite_line(self, line, page):
        """Code spans are masked first (a link whose label is a code span must still be rewritten, and a link written inside a code span must
        not be), then restored."""
        spans = []

        def mask(m):
            spans.append(m.group(0))
            return f"\x00{len(spans) - 1}\x00"
        masked = self._CODE_SPAN.sub(mask, line)
        masked = self._rewrite_plain(masked, page)
        return re.sub(r"\x00(\d+)\x00", lambda m: spans[int(m.group(1))], masked)

    def _rewrite_plain(self, text, page):
        def inline(m):
            bang, label, href, title = m.groups()
            raw = href[1:-1] if href.startswith("<") else href
            return f"{bang}{label}({self.resolve(raw, page, is_image=bool(bang))}{title})"

        def refdef(m):
            return f"{m.group(1)}{self.resolve(m.group(2), page)}{m.group(3)}"

        def attr(m):
            return f"{m.group(1)}={m.group(2)}{self.resolve(m.group(3), page, is_image=m.group(1) == 'src')}{m.group(2)}"
        text = self._INLINE.sub(inline, text)
        text = self._REFDEF.sub(refdef, text)
        return self._HTMLATTR.sub(attr, text)


def github_anchor(heading):
    """GitHub's heading id: lower case, markup and punctuation dropped, spaces to hyphens."""
    text = re.sub(r"<[^>]+>|[`*]", "", heading)
    text = re.sub(r"(?<!\w)_|_(?!\w)", "", text).strip().lower()      # emphasis underscores go; an underscore inside a word (a tool name) stays
    text = re.sub(r"[^\w\- ]", "", text, flags=re.UNICODE)
    return text.replace(" ", "-")


def anchors_of(markdown_text):
    seen, out = {}, set()
    for m in re.finditer(r"^#{1,6}\s+(.+?)\s*#*\s*$", markdown_text, flags=re.M):
        base = github_anchor(m.group(1))
        n = seen.get(base, 0)
        seen[base] = n + 1
        out.add(base if n == 0 else f"{base}-{n}")
    out.update(re.findall(r'<a\s+(?:id|name)="([^"]+)"', markdown_text))          # explicit anchors, as the changelog uses
    return out


def banner(page, linker):
    if page.mirror:
        src = page.spec["path"]
        return (f"> This page mirrors [`{src}`]({linker.github(src)}) from the repository and is regenerated on every merge to `main`. "
                "To correct it, edit that file; changes made here are overwritten.\n\n")
    if page.generated:
        return "> This page is generated from the repository on every merge to `main`; changes made here are overwritten.\n\n"
    if page.slug == "index":
        return ""
    return (f"> This page comes from [`{page.src}`]({linker.github(page.src)}) in the repository and is regenerated on every merge to `main`. "
            "To correct it, edit that file; changes made here are overwritten.\n\n")


def sidebar(sections, names):
    lines = ["**[Documentation home](Home)**", ""]
    for title, pages in sections:
        lines.append(f"**{title}**")
        lines.append("")
        lines += [f"- [{p.title}]({names[p.slug]})" for p in pages]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def footer(facts):
    sha = os.environ.get("GITHUB_SHA", "")
    if not sha:
        try:
            sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()  # noqa: S607 -- fixed git call, no user input
        except (OSError, subprocess.CalledProcessError):
            sha = "unknown"
    return (f"Cartogen AI {facts['version']} · generated from the [repository]({GITHUB}) at commit `{sha[:10]}` on {facts['build_date']} · "
            "this wiki is rebuilt on every merge to `main`; edits made in the browser are overwritten, so correct the source files instead.\n")


def build_wiki(out_dir, facts):
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    ctx, sections, pages, _home = B.assemble(facts)
    sources = B.markdown_sources(pages, ctx, facts)
    # The HTML site's home page is styled with classes and cards that GitHub's wiki would strip, so the wiki has its own plain-Markdown home.
    _meta, wiki_home = B.strip_front_matter((SITE / "wiki-home.md").read_text(encoding="utf-8"))
    sources["index"] = B.fill_facts(wiki_home, facts)
    names = page_names(pages)
    linker = WikiLinker(pages, names)
    texts = {}
    for page in pages.values():
        body = linker.rewrite(sources[page.slug], page)
        texts[page.slug] = banner(page, linker) + body.strip("\n") + "\n"
        (out_dir / f"{names[page.slug]}.md").write_text(texts[page.slug], encoding="utf-8")
    (out_dir / "_Sidebar.md").write_text(sidebar(sections, names), encoding="utf-8")
    (out_dir / "_Footer.md").write_text(footer(facts), encoding="utf-8")
    return pages, names, linker, texts


def strip_code(text):
    """The text without fenced code blocks and inline code, so an example link inside code is not mistaken for a real one."""
    out, fence = [], None
    for line in text.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            fence = None if fence == marker else (fence or marker)
            continue
        if not fence:
            out.append(WikiLinker._CODE_SPAN.sub("", line))
    return "\n".join(out)


def check_wiki(out_dir, pages, names, linker, texts):
    """Errors: link-rewriting errors and any link to a wiki page that was not written. Warnings: a #fragment that matches no heading."""
    errors, warnings = list(linker.errors), list(linker.warnings)
    written = {p.stem for p in out_dir.glob("*.md")}
    anchors = {names[s]: anchors_of(t) for s, t in texts.items()}
    inline = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)")
    for page in pages.values():
        for href in inline.findall(strip_code(texts[page.slug])):
            if _EXTERNAL.match(href):
                continue
            target, _, frag = href.partition("#")
            dest = target or names[page.slug]
            if dest not in written:
                errors.append(f"{page.slug}: link {href} -> no wiki page {dest}")
            elif frag and frag not in anchors.get(dest, set()):
                warnings.append(f"{page.slug}: {href} -> no heading #{frag} on {dest}")
    return errors, warnings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(SITE / "_wiki"))
    ap.add_argument("--check", action="store_true", help="exit 1 on a broken internal link")
    args = ap.parse_args()
    facts = B.collect_facts()
    out = Path(args.out).resolve()
    pages, names, linker, texts = build_wiki(out, facts)
    errors, warnings = check_wiki(out, pages, names, linker, texts)
    print(f"wrote {len(pages)} wiki pages into {out} ({facts['version']}, {facts['tools']} tools)")
    for w in warnings[:25]:
        print("warning:", w)
    if len(warnings) > 25:
        print(f"warning: ... and {len(warnings) - 25} more")
    for e in errors:
        print("ERROR:", e)
    if errors and args.check:
        print(f"{len(errors)} link error(s)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
