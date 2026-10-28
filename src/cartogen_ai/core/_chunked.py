"""Cooperative chunking for loops that must run on QGIS's GUI thread.

Why (2026-10-12 processing-cost audit, docs/PROCESSING_COST_AUDIT_2026-10-12.md): tools run on the GUI thread, and `processEvents` was
called nowhere, so any loop over features, pairs or pixels froze QGIS for as long as it ran ("Not Responding", no Stop). The loops touch
QgsVectorLayer/QgsFeature objects, which are only safe on the GUI thread, so they cannot be moved to a worker (that is what
_background_processing.run_callable is for, and it is only valid for work with no QGIS objects). The remedy for those loops is to
SPLIT THE WORK INTO SMALL SLICES: after every slice of about 50 ms the loop hands control back to Qt (the window repaints, Stop is
heard), checks whether the user pressed Stop, and now and then reports progress.

    for feat in features(layer, "Classifying facilities"):      # a drop-in for layer.getFeatures()
        ...
    for pair in chunked(pairs, "Scoring pairs", total=n):      # any iterable
        ...
    y = Yielder("Matrix rows", total=n)                          # or tick by hand where a loop is awkward to wrap
    ... y.tick() ...

Pressing Stop raises _background_processing.AnalysisCancelledError, which every tool already lets through to the dispatcher. Off the
GUI thread (a worker, tests) nothing is pumped: the loop just runs. Pure Python apart from the optional Qt import; the clock, the pump,
the cancel check and the progress report are all injectable, which is how the offline tests exercise it."""
import time

from . import cancel_signal
from ._background_processing import AnalysisCancelledError, QGIS_AVAILABLE, _on_gui_thread

if QGIS_AVAILABLE:
    from qgis.PyQt.QtCore import QCoreApplication

SLICE_SECONDS = 0.05          # how long a loop may run before it hands control back to Qt
REPORT_SECONDS = 3.0          # how often progress is announced
CHECK_EVERY = 64              # items between clock reads: a monotonic() call per feature would itself cost


def _default_pump():
    if QGIS_AVAILABLE and _on_gui_thread():
        QCoreApplication.processEvents()


class Yielder:
    """Counts work items and, once per slice, pumps Qt, honours Stop and reports progress. One per loop; cheap to call."""

    def __init__(self, label="Working", total=None, slice_s=SLICE_SECONDS, report_s=REPORT_SECONDS, check_every=CHECK_EVERY,
                 clock=time.monotonic, pump=None, cancelled=None, report=None):
        self.label = label
        self.total = total
        self.count = 0
        self.pumps = 0
        self._slice, self._report_every, self._check_every = slice_s, report_s, max(1, int(check_every))
        self._clock = clock
        self._pump = _default_pump if pump is None else pump
        self._cancelled = cancel_signal.is_cancelled if cancelled is None else cancelled
        self._report = cancel_signal.report if report is None else report
        now = clock()
        self._last_pump = now
        self._last_report = now
        self._started = now

    def tick(self, n=1):
        """Call once per work item (or per `n` items). Raises AnalysisCancelledError when the user pressed Stop."""
        before = self.count
        self.count += n
        if self.count // self._check_every == before // self._check_every:
            return
        now = self._clock()
        if now - self._last_pump < self._slice:
            return
        self._last_pump = now
        self.pumps += 1
        self._pump()
        if self._cancelled():
            raise AnalysisCancelledError(f"{self.label}: stopped by the user after {self.count:,} items.")
        if now - self._last_report >= self._report_every:
            self._last_report = now
            of = f" of {self.total:,}" if self.total else ""
            self._report(f"{self.label}: {self.count:,}{of} done, {now - self._started:.0f}s (press Stop to cancel)")


def chunked(iterable, label="Working", total=None, **kwargs):
    """Yield the items of `iterable`, giving Qt a turn between slices of work (see the module docstring)."""
    y = Yielder(label, total=total, **kwargs)
    for item in iterable:
        y.tick()
        yield item


def features(layer, label="Working", request=None, **kwargs):
    """A drop-in for `layer.getFeatures()` (or `layer.getFeatures(request)`) that keeps QGIS responsive and honours Stop."""
    try:
        total = int(layer.featureCount())
    except Exception:
        total = None
    return chunked(layer.getFeatures(request) if request is not None else layer.getFeatures(), label, total=total, **kwargs)


def ensure_within(count, limit, what, advice="Clip or filter the input first."):
    """Raise ValueError with a plain message when `count` (a number of items, pairs or values) is over `limit`. Pure.

    The one place a tool states a work budget, so the wording is the same everywhere and a refusal says what to do."""
    if count > limit:
        raise ValueError(f"{what} is {count:,}, above the {limit:,} this tool will attempt. {advice}")
