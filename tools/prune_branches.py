#!/usr/bin/env python3
"""Prune the stale remote branches approved in master-list row HY-4 (owner said "go" on 2026-11-09), safely and reversibly.

    python tools/prune_branches.py              # dry run: verifies every branch against the live remote and prints what it would do
    python tools/prune_branches.py --execute    # tags where needed, then deletes, one branch at a time, stopping at the first refusal

Run it from a clone with push rights to the repository's `origin` (it was written in a cloud session whose git proxy answers HTTP 403 to every
push except the session's own branch, so the session could not run it). Standard library plus git.

The branch list is read from docs/BRANCH_PRUNE_DRYRUN_2026-11-09.md, sections 1 and 2. Per branch, against `git ls-remote` at the moment it runs:
- Section 1 (merged): deleted only if the branch tip equals the head ref of one of its pull requests (`refs/pull/N/head`), because GitHub keeps
  those commits whatever happens to the branch.
- Section 2, a pull request closed without merging: deleted only if the branch tip equals that pull request's head ref, same reason.
- Section 2, anything else (no pull request, or a merged one with later commits): the commits exist only on the branch, so a tag
  `archive/<name>` is created and pushed FIRST and checked on the remote; the branch is deleted only after that. Recreate one with
  `git branch claude/<name> archive/<name>`.
A branch whose tip moved since the dry run, or that fails its check, is skipped and reported, never deleted. `main`, the current branch and any
branch not named `claude/...` are never touched."""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "BRANCH_PRUNE_DRYRUN_2026-11-09.md"
_ROW = re.compile(r"^\| `(claude/[^`]+)` \| ([^|]+)\|", re.M)


def read_plan(text):
    """([(branch, [pr numbers])] of section 1, [(branch, state text)] of section 2) from the dry-run document. Pure."""
    s1 = text.split("## 1.")[1].split("## 2.")[0]
    s2 = text.split("## 2.")[1].split("## 3.")[0]
    merged = [(b, [int(n) for n in re.findall(r"\d+", prs)]) for b, prs in _ROW.findall(s1)]
    undecided = [(b, state.strip()) for b, state in _ROW.findall(s2)]
    return merged, undecided


def decide(branch, state, tip, pull_heads, current_branch=""):
    """What to do with one branch: ('delete', why), ('tag_then_delete', why) or ('skip', why). Pure.

    `state` is the section-2 text ('' for a section-1 branch, whose pull request numbers are in `state` as digits instead)."""
    if not branch.startswith("claude/") or branch == current_branch:
        return "skip", "not a claude/ branch or the current branch"
    if tip is None:
        return "skip", "no longer on the remote"
    numbers = [int(n) for n in re.findall(r"#?(\d+)", state)]
    on_pr_head = any(pull_heads.get(n) == tip for n in numbers)
    if state.strip() and re.search(r"[A-Za-z]", state):             # a section-2 row
        if "closed, never merged" in state and on_pr_head:
            return "delete", "closed pull request keeps the same commit"
        return "tag_then_delete", "commits exist only on the branch"
    if on_pr_head:                                                   # a section-1 row (digits only)
        return "delete", "tip equals its merged pull request's head"
    return "skip", "tip is not any pull request head (moved since the dry run?)"


def _git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)  # noqa: S603, S607 -- fixed argv, no shell


def remote_state():
    heads = {}
    for line in _git("ls-remote", "--heads", "origin").stdout.splitlines():
        sha, ref = line.split()
        heads[ref[len("refs/heads/"):]] = sha
    pulls = {}
    for line in _git("ls-remote", "origin", "refs/pull/*/head").stdout.splitlines():
        sha, ref = line.split()
        pulls[int(ref.split("/")[2])] = sha
    return heads, pulls


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--execute", action="store_true", help="really tag and delete; without it only a plan is printed")
    args = parser.parse_args(argv)
    merged, undecided = read_plan(DOC.read_text(encoding="utf-8"))
    heads, pulls = remote_state()
    current = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    todo = [(b, " ".join(str(n) for n in nums)) for b, nums in merged] + list(undecided)
    counts = {"delete": 0, "tag_then_delete": 0, "skip": 0, "done": 0, "failed": 0}
    for branch, state in todo:
        action, why = decide(branch, state, heads.get(branch), pulls, current)
        counts[action] += 1
        print(f"{action:16} {branch}  ({why})")
        if not args.execute or action == "skip":
            continue
        tip = heads[branch]
        if action == "tag_then_delete":
            tag = "archive/" + branch.split("/", 1)[1]
            made = _git("tag", "-a", tag, tip, "-m", f"Archive of {branch} at {tip} before deletion (HY-4). Recreate: git branch {branch} {tag}")
            if made.returncode != 0 and "already exists" not in made.stderr:
                print(f"  STOP: could not create tag {tag}: {made.stderr.strip()}")
                return 1
            if _git("push", "origin", f"refs/tags/{tag}").returncode != 0 or tip not in _git("ls-remote", "origin", f"refs/tags/{tag}^{{}}").stdout:
                print(f"  STOP: tag {tag} is not on the remote with the right commit; the branch was NOT deleted.")
                return 1
        if _git("push", "origin", "--delete", branch).returncode != 0:
            print(f"  STOP: the remote refused to delete {branch}.")
            counts["failed"] += 1
            return 1
        counts["done"] += 1
    print("\n" + ", ".join(f"{k}: {v}" for k, v in counts.items()))
    if not args.execute:
        print("Dry run only. Nothing was changed. Add --execute to apply it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
