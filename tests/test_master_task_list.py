"""The master task list's CSV, Markdown tables and counts must agree.

Guards the standing duty in CLAUDE.md: the list is edited with
`python tools/master_list.py set ...`, never by hand in only one file.
"""

import glob
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import master_list  # noqa: E402


class MasterTaskListTests(unittest.TestCase):
    def test_csv_and_markdown_agree(self):
        lists = sorted(glob.glob(os.path.join(ROOT, "docs", "MASTER_TASK_LIST_*.md")))
        self.assertTrue(lists, "no docs/MASTER_TASK_LIST_*.md found")
        md = lists[-1]
        self.assertEqual(master_list.problems(md, md[:-3] + ".csv"), [])


if __name__ == "__main__":
    unittest.main()
