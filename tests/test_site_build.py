"""The documentation site (site/build.py, GitHub Pages): it builds, every internal link and anchor resolves, the numbers on it match the
code, and nothing authored is orphaned. Skipped when the `markdown` package is not installed (it is a docs-build dependency, not a plugin
one). The same check runs as `python site/build.py --check` in the docs-site workflow."""
import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HAVE_MARKDOWN = importlib.util.find_spec("markdown") is not None


def _load_build():
    spec = importlib.util.spec_from_file_location("cartogen_site_build", REPO / "site" / "build.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@unittest.skipUnless(HAVE_MARKDOWN, "needs the `markdown` package (docs build only)")
class TestSiteBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = _load_build()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "_site"
        cls.facts = cls.build.collect_facts()
        cls.pages, cls.linker = cls.build.build(cls.out, cls.facts)
        cls.errors, cls.warnings = cls.build.check_links(cls.out, cls.pages, cls.linker)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_no_broken_internal_links_or_anchors_in_authored_and_generated_pages(self):
        self.assertEqual(self.errors, [])

    def test_the_essential_files_exist(self):
        for name in ("index.html", "404.html", "search-index.js", ".nojekyll", "assets/style.css", "assets/site.js", "assets/mark.svg"):
            self.assertTrue((self.out / name).is_file(), name)

    def test_every_page_in_the_nav_was_written(self):
        for page in self.pages.values():
            self.assertTrue((self.out / page.url).is_file(), page.url)
        self.assertGreaterEqual(len(self.pages), 45)

    def test_every_authored_file_is_in_the_nav_so_none_is_orphaned(self):
        used = {p.spec["file"] for p in self.pages.values() if p.spec.get("file")}
        used |= {"reference/task-register.md", "humanitarian/workflows.md", "project/documents.md"}      # read by their generators
        on_disk = {p.relative_to(REPO / "site" / "content").as_posix() for p in (REPO / "site" / "content").rglob("*.md")}
        self.assertEqual(on_disk - used, set())

    def test_the_numbers_on_the_site_match_the_code(self):
        import sys
        sys.path.insert(0, str(REPO / "src"))
        import importlib
        importlib.import_module("cartogen_ai.core.agent.tools")
        from cartogen_ai.core.agent.tools import registry
        self.assertEqual(self.facts["tools"], len(registry.TOOL_REGISTRY), "docs/TOOLS_REFERENCE.md is out of date: run docs/generate_tools_reference.py")
        register = json.loads((REPO / "src/cartogen_ai/core/agent/task_register.json").read_text(encoding="utf-8"))
        self.assertEqual(self.facts["tasks"], len(register))
        home = (self.out / "index.html").read_text(encoding="utf-8")
        self.assertIn(f"<b>{self.facts['tools']}</b>", home)
        self.assertIn(self.facts["version"], home)

    def test_every_registered_tool_has_a_place_in_the_tool_reference(self):
        import sys
        sys.path.insert(0, str(REPO / "src"))
        from cartogen_ai.core.agent.tools import registry
        text = "".join((self.out / "tools" / f).read_text(encoding="utf-8") for f in [p.name for p in (self.out / "tools").glob("*.html")])
        missing = [n for n in registry.TOOL_REGISTRY if f">{n}<" not in text.replace("<code>", ">").replace("</code>", "<") and n not in text]
        self.assertEqual(missing, [])

    def test_the_search_index_is_valid_and_covers_every_page(self):
        raw = (self.out / "search-index.js").read_text(encoding="utf-8")
        data = json.loads(re.sub(r"^window\.SEARCH_INDEX=|;$", "", raw))
        self.assertEqual(len(data), len(self.pages))
        for entry in data:
            self.assertTrue(entry["t"] and entry["u"].endswith(".html"))

    def test_mirrored_pages_say_which_file_they_mirror(self):
        page = (self.out / "security" / "policy.html").read_text(encoding="utf-8")
        self.assertIn("SECURITY.md", page)
        self.assertIn("mirrors", page)

    def test_images_in_mirrored_documents_are_copied_into_the_site(self):
        self.assertTrue((self.out / "assets" / "repo" / "docs" / "images" / "dock-panel.png").is_file())

    def test_a_list_straight_after_a_paragraph_becomes_a_list(self):
        text = self.build.blank_line_before_lists("Two buttons:\n- one\n- two\n\n```\nnot:\n- code\n```")
        self.assertIn("Two buttons:\n\n- one", text)
        self.assertIn("not:\n- code", text)             # inside a code fence nothing is touched


@unittest.skipUnless(HAVE_MARKDOWN, "needs the `markdown` package (docs build only)")
class TestAuthoredLinkRules(unittest.TestCase):
    def test_an_unknown_page_link_is_an_error_not_silently_kept(self):
        build = _load_build()
        pages = {"a": build.Page({"slug": "a", "title": "A", "kind": "content"}, "S")}
        linker = build.Linker(pages, Path(tempfile.mkdtemp()))
        linker.resolve("@nope", pages["a"], "href")
        self.assertTrue(any("unknown page" in e for e in linker.errors))
        linker.resolve("plain.md", pages["a"], "href")
        self.assertTrue(any("must use" in e for e in linker.errors))


class TestSiteIsNotShipped(unittest.TestCase):
    def test_the_plugin_zip_excludes_the_site_folder(self):
        text = (REPO / "plugin_upload.py").read_text(encoding="utf-8")
        self.assertRegex(text, r'EXCLUDE_ROOT_ONLY_DIRS\s*=\s*\{[^}]*"site"')


if __name__ == "__main__":
    unittest.main()
