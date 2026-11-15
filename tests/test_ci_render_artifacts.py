"""Master list DEF-1 (#379): the elevation-profile print item rendered empty intermittently in the CI live job, twice on one commit and not on a third run of the same commit. The
cause was never found because the picture was never kept: the render test printed a number and a base64 text into a log. This pins the plumbing that keeps the picture:
the live render tests save their PNGs through tests/_render_artifacts.save_png into $CARTOGEN_LIVE_ARTIFACTS, and the live job uploads that folder whatever the result.
Offline. What it cannot show: why the render is sometimes empty; the next occurrence will now leave the picture to look at."""
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests import _render_artifacts as ra   # noqa: E402


class FakeImage:
    def __init__(self, ok=True):
        self.ok, self.saved = ok, []

    def save(self, path, fmt):
        self.saved.append((path, fmt))
        if self.ok:
            Path(path).write_bytes(b"\x89PNG fake")
        return self.ok


class TestSavePng(unittest.TestCase):
    def test_nothing_is_written_when_the_folder_is_not_set(self):
        image = FakeImage()
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ra.ENV, None)
            self.assertIsNone(ra.save_png("profile_render_1", image))
        self.assertEqual(image.saved, [])

    def test_the_picture_is_written_into_the_folder_as_a_png(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, {ra.ENV: str(Path(folder) / "sub")}):
            image = FakeImage()
            path = ra.save_png("profile_render_1", image)
            self.assertEqual(Path(path).name, "profile_render_1.png")
            self.assertTrue(Path(path).is_file())
            self.assertEqual(image.saved[0][1], "PNG")

    def test_an_awkward_name_cannot_write_outside_the_folder(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, {ra.ENV: folder}):
            path = ra.save_png("../../etc/pass wd:1", FakeImage())
            self.assertEqual(Path(path).parent, Path(folder))
            self.assertRegex(Path(path).name, r"^[A-Za-z0-9_.-]+\.png$")

    def test_a_failed_save_is_reported_as_none_not_a_path(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, {ra.ENV: folder}):
            self.assertIsNone(ra.save_png("x", FakeImage(ok=False)))


class TestTheLiveJobKeepsThePictures(unittest.TestCase):
    """Reads the workflow as text, on purpose: PyYAML is not installed in the CI test jobs, so a test that imported it failed there (PR 574, 2026-11-05)."""

    @classmethod
    def setUpClass(cls):
        cls.text = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
        start = cls.text.index("  qgis-live-tests:")
        following = [m.start() for m in re.finditer(r"^  [A-Za-z0-9_-]+:\s*$", cls.text[start + 10:], re.M)]
        cls.job = cls.text[start:(start + 10 + following[0]) if following else len(cls.text)]

    def test_the_job_sets_the_folder_the_tests_write_to(self):
        self.assertIn(f"      {ra.ENV}: /tmp/cartogen_live_artifacts", self.job)

    def test_there_is_exactly_one_upload_step_and_it_keeps_the_folder_whatever_the_result(self):
        self.assertEqual(self.job.count("uses: actions/upload-artifact@"), 1)
        step = self.job[self.job.index("- name: Keep the pictures the live render tests made"):]
        self.assertRegex(step, r"(?m)^        if: always\(\)\s*$")
        self.assertRegex(step, r"(?m)^        continue-on-error: true")          # a diagnostic upload must never fail the live job
        self.assertIn("          path: /tmp/cartogen_live_artifacts", step)
        self.assertIn("          if-no-files-found: ignore", step)

    def test_the_folder_in_the_step_is_the_folder_in_the_env(self):
        env = re.search(rf"{ra.ENV}: (\S+)", self.job).group(1)
        self.assertIn(f"path: {env}", self.job)

    def test_the_render_tests_save_their_pictures_through_the_helper(self):
        text = (ROOT / "tests" / "test_layout_items_render_live.py").read_text(encoding="utf-8")
        self.assertIn("save_png(", text)
        self.assertGreaterEqual(text.count("_keep("), 3)          # the definition and the two render tests that call it


if __name__ == "__main__":
    unittest.main()
