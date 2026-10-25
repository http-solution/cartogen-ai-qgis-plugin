"""The GitHub wiki export (site/build_wiki.py): every page is written, every link between pages resolves, repository links and images are
rewritten, code is left alone, the page names are safe, and the workflow no longer deploys GitHub Pages. Skipped when the `markdown` package is
not installed (the page model comes from site/build.py, a docs-build dependency)."""
import importlib.util
import re
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HAVE_MARKDOWN = importlib.util.find_spec("markdown") is not None


def _load():
    spec = importlib.util.spec_from_file_location("cartogen_site_build_wiki", REPO / "site" / "build_wiki.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@unittest.skipUnless(HAVE_MARKDOWN, "needs the `markdown` package (docs build only)")
class TestWikiBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = _load()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "_wiki"
        cls.facts = cls.w.B.collect_facts()
        cls.pages, cls.names, cls.linker, cls.texts = cls.w.build_wiki(cls.out, cls.facts)
        cls.errors, cls.warnings = cls.w.check_wiki(cls.out, cls.pages, cls.names, cls.linker, cls.texts)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_no_broken_links_between_wiki_pages(self):
        self.assertEqual(self.errors, [])

    def test_home_sidebar_footer_and_every_page_are_written(self):
        for name in ("Home", "_Sidebar", "_Footer"):
            self.assertTrue((self.out / f"{name}.md").is_file(), name)
        for slug, name in self.names.items():
            self.assertTrue((self.out / f"{name}.md").is_file(), slug)
        self.assertEqual(len(list(self.out.glob("*.md"))), len(self.pages) + 2)

    def test_page_names_are_unique_and_safe_in_a_markdown_link(self):
        names = list(self.names.values())
        self.assertEqual(len(names), len(set(names)))
        for name in names:
            self.assertRegex(name, r"^[\w][\w.\-]*$", name)           # no spaces, parentheses, ampersands or slashes
        self.assertEqual(self.names["index"], "Home")

    def test_no_authoring_link_syntax_survives_outside_code(self):
        for slug, text in self.texts.items():
            visible = self.w.strip_code(text)
            self.assertNotRegex(visible, r"\]\((@|repo:|asset:)", slug)
            self.assertNotRegex(visible, r'href="(@|repo:|asset:)', slug)

    def test_repository_images_become_raw_urls_and_files_become_github_links(self):
        linker = self.linker
        page = self.pages["install"]
        self.assertEqual(linker.rewrite("![x](repo:branding/cartogen-mark.svg)", page),
                         f"![x]({self.w.RAW}/branding/cartogen-mark.svg)")
        self.assertEqual(linker.rewrite("[s](repo:LICENSE)", page), f"[s]({self.w.GITHUB}/blob/main/LICENSE)")
        self.assertEqual(linker.rewrite("[a](@architecture/agent-loop#x)", page), f"[a]({self.names['architecture/agent-loop']}#x)")

    def test_code_is_left_alone_and_a_link_with_a_code_label_is_rewritten(self):
        linker = self.linker
        page = self.pages["install"]
        self.assertEqual(linker.rewrite("`[a](@install)` and\n```\n[a](@install)\n```", page), "`[a](@install)` and\n```\n[a](@install)\n```")
        self.assertEqual(linker.rewrite("[`x`](@install)", page), f"[`x`]({self.names['install']})")
        self.assertEqual(linker.rewrite("[web](https://example.org/a) [top](#top)", page), "[web](https://example.org/a) [top](#top)")

    def test_an_unknown_page_or_a_bare_relative_link_in_an_authored_page_is_an_error(self):
        probe = self.w.WikiLinker(self.pages, self.names)
        probe.rewrite("[a](@no/such/page) [b](plain.md)", self.pages["install"])
        self.assertEqual(len(probe.errors), 2)

    def test_the_home_page_is_plain_markdown_without_the_html_sites_styling(self):
        home = (self.out / "Home.md").read_text(encoding="utf-8")
        self.assertNotIn('class="', home)
        self.assertIn(f"Version {self.facts['version']}", home)

    def test_the_footer_says_edits_in_the_browser_are_overwritten(self):
        self.assertIn("overwritten", (self.out / "_Footer.md").read_text(encoding="utf-8"))


class TestWorkflowPublishesTheWikiNotPages(unittest.TestCase):
    def test_the_docs_workflow_syncs_the_wiki_and_no_longer_deploys_pages(self):
        text = (REPO / ".github" / "workflows" / "docs-site.yml").read_text(encoding="utf-8")
        self.assertIn("build_wiki.py", text)
        self.assertIn(".wiki.git", text)
        self.assertNotIn("deploy-pages", text)
        self.assertNotIn("upload-pages-artifact", text)
        self.assertNotIn("pages: write", text)

    def test_only_the_sync_job_can_write_and_it_does_not_run_on_pull_requests(self):
        text = (REPO / ".github" / "workflows" / "docs-site.yml").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"contents: write", text)), 1)
        self.assertIn("if: github.event_name != 'pull_request'", text)


if __name__ == "__main__":
    unittest.main()
