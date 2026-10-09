# -*- coding: utf-8 -*-
"""Several separate requests pasted into one message become a queue of jobs, each run on its own.

Why (2026-10-09): five unrelated analyses (Marib, Hadramawt, Aden, Taizz, the coastal highway) pasted as one message were run as ONE
turn: a single task matched the whole text, one tool list served five jobs, and the turn spent its whole round budget. Splitting is
conservative on purpose. Several places or datasets can belong to ONE analysis, so a sentence count never splits a request: only
explicit job boundaries do (numbered or headed blocks that are each a full request, or blank-line-separated paragraphs that are each
a full request). Short numbered lists ("1. fetch roads 2. buffer 3. export") are steps of one analysis and are left alone.

Pure (stdlib only): the chat widget owns the confirmation card and the sequencing."""
import re

from .capabilities import needed_capabilities

MIN_JOB_WORDS = 20          # a job is a whole request, not a step
MIN_JOBS = 2
_NUMBER_AT_LINE_START = re.compile(r"(?m)^[ \t]*(?:(?:scenario|task|job|request|case|example)[ \t]*)?(\d{1,2})[ \t]*[.):\-][ \t]+", re.I)
_BLANK_LINE = re.compile(r"\n[ \t]*\n+")


def _words(text):
    return len(text.split())


def _looks_like_a_request(block):
    """A block is a request when it is long enough and names at least two actions or data sources (capabilities)."""
    return _words(block) >= MIN_JOB_WORDS and len(needed_capabilities(block)) >= 2


def _split_numbered(text):
    matches = list(_NUMBER_AT_LINE_START.finditer(text))
    numbers = [int(m.group(1)) for m in matches]
    if len(matches) < MIN_JOBS or numbers != list(range(numbers[0], numbers[0] + len(numbers))) or numbers[0] != 1:
        return None
    bounds = [m.start() for m in matches] + [len(text)]
    blocks = [text[bounds[i]:bounds[i + 1]].strip() for i in range(len(matches))]
    blocks = [_NUMBER_AT_LINE_START.sub("", b, count=1).strip() for b in blocks]
    return blocks if all(_looks_like_a_request(b) for b in blocks) else None


def _split_paragraphs(text):
    blocks = [b.strip() for b in _BLANK_LINE.split(text.strip()) if b.strip()]
    if len(blocks) < MIN_JOBS:
        lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
        blocks = lines if len(lines) >= 3 else blocks            # one request per line, three or more lines
    return blocks if len(blocks) >= MIN_JOBS and all(_looks_like_a_request(b) for b in blocks) else None


def split_jobs(text):
    """The list of job texts when `text` holds two or more separate requests, else None. Pure."""
    text = (text or "").strip()
    if _words(text) < 2 * MIN_JOB_WORDS:
        return None
    return _split_numbered(text) or _split_paragraphs(text)


def preview_text(jobs, width=90):
    """Numbered one-line summaries for the confirmation card."""
    rows = []
    for i, job in enumerate(jobs, 1):
        one = " ".join(job.split())
        rows.append(f"{i}. {one[:width]}{'...' if len(one) > width else ''}")
    return "\n".join(rows)


class JobQueue:
    """Ordered jobs with their own status; pure state, no Qt."""

    def __init__(self, jobs):
        self.jobs = list(jobs)
        self.status = ["pending"] * len(self.jobs)
        self.current = None

    def __len__(self):
        return len(self.jobs)

    def next_pending(self):
        """Mark the next pending job as running and return (index, text), or None when nothing is left."""
        for i, state in enumerate(self.status):
            if state == "pending":
                self.status[i] = "running"
                self.current = i
                return i, self.jobs[i]
        self.current = None
        return None

    def finish_current(self, ok):
        if self.current is not None:
            self.status[self.current] = "done" if ok else "failed"
        self.current = None

    def pending_count(self):
        return self.status.count("pending")

    def keep_only_first(self):
        self.jobs, self.status = self.jobs[:1], self.status[:1]

    def summary(self):
        done, failed = self.status.count("done"), self.status.count("failed")
        return f"{done} done, {failed} failed, {self.pending_count()} not run, of {len(self.jobs)}"
