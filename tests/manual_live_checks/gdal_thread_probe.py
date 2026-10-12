"""One experiment per process: does a Python-implemented Processing algorithm (gdal:slope) survive a worker thread?

Run by tests/test_gdal_thread_probe_live.py, one fresh process per attempt, so a segfault ends only that attempt and faulthandler prints the Python
stack of the thread that crashed (2026-10-12 investigation of the PR #249/#251 finding that gdal:slope on a worker crashed the QGIS 4.2.2 live job
in 2 of 4 runs; cause never found). Not a unit test: it prints evidence.

    python gdal_thread_probe.py <variant> [gui|nogui] [repeats]

variants:  flags            print the algorithm's flags (is FlagNoThreading set?) and what kind of object it is
           sync             processing.run on the calling thread (control)
           bg_current       what cartogen_ai does today: QgsProcessingAlgRunnerTask + a Python QgsProcessingFeedback subclass + nested QEventLoop
           bg_cpp_feedback  the same with a plain C++ QgsProcessingFeedback (tests: is the Python feedback subclass called from the worker the crash?)
           bg_poll          the same as bg_cpp_feedback but waits by polling processEvents instead of a nested QEventLoop.exec
           bg_keepalive     bg_cpp_feedback, and every object the task touches is kept alive in a module list until exit (tests a premature free)
"""
import faulthandler
import os
import sys
import tempfile
import time

faulthandler.enable(all_threads=True)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "src"))
sys.path.insert(0, os.path.join(HERE, "..", ".."))

variant = sys.argv[1] if len(sys.argv) > 1 else "flags"
gui = (sys.argv[2] == "gui") if len(sys.argv) > 2 else False
repeats = int(sys.argv[3]) if len(sys.argv) > 3 else 3
if gui:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qgis.core import (  # noqa: E402
    QgsApplication, QgsProcessingAlgorithm, QgsProcessingAlgRunnerTask, QgsProcessingContext, QgsProcessingFeedback, QgsProject,
)
from qgis.PyQt.QtCore import QCoreApplication, QEventLoop, QTimer  # noqa: E402

app = QgsApplication([b"gdalprobe"], gui)
QgsApplication.setPrefixPath("/usr", True)
app.initQgis()
from processing.core.Processing import Processing  # noqa: E402
Processing.initialize()
import processing  # noqa: E402

KEEP = []


def make_dem(path, n=400):
    import numpy
    from osgeo import gdal, osr
    ds = gdal.GetDriverByName("GTiff").Create(path, n, n, 1, gdal.GDT_Float32)
    ds.SetGeoTransform((500000.0, 30.0, 0.0, 1700000.0, 0.0, -30.0))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(32638)
    ds.SetProjection(srs.ExportToWkt())
    xs = numpy.linspace(0, 12, n)
    ds.GetRasterBand(1).WriteArray((numpy.sin(xs)[None, :] * 80 + numpy.cos(xs)[:, None] * 60 + 500).astype("float32"))
    ds.FlushCache()
    return path


tmp = tempfile.mkdtemp(prefix="gdalprobe_")
dem = make_dem(os.path.join(tmp, "dem.tif"))


def params(i):
    return {"INPUT": dem, "BAND": 1, "SCALE": 1.0, "AS_PERCENT": False, "COMPUTE_EDGES": False, "ZEVENBERG": False, "TRIG": False,
            "OUTPUT": os.path.join(tmp, f"slope_{i}.tif")}


def make_context():
    ctx = QgsProcessingContext()
    ctx.setProject(QgsProject.instance())
    return ctx


def run_task(i, feedback, wait, keep=False):
    alg = QgsApplication.processingRegistry().createAlgorithmById("gdal:slope")
    ctx = make_context()
    task = QgsProcessingAlgRunnerTask(alg, params(i), ctx, feedback)
    if keep:
        KEEP.extend([alg, ctx, task, feedback])
    state = {"done": False, "ok": None, "results": None}

    def on_executed(ok, results):
        state.update(done=True, ok=bool(ok), results=results)
    task.executed.connect(on_executed)
    QgsApplication.taskManager().addTask(task)
    deadline = time.monotonic() + 90
    if wait == "loop":
        loop = QEventLoop()
        timer = QTimer()
        timer.setInterval(50)

        def tick():
            if state["done"] or time.monotonic() > deadline:
                loop.quit()
        timer.timeout.connect(tick)
        task.executed.connect(lambda *a: loop.quit())
        timer.start()
        loop.exec()
        timer.stop()
    else:
        while not state["done"] and time.monotonic() < deadline:
            QCoreApplication.processEvents()
            time.sleep(0.01)
    return state


if variant == "flags":
    alg = QgsApplication.processingRegistry().createAlgorithmById("gdal:slope")
    flags = alg.flags()
    print("PROBE flags", int(flags), "class", type(alg).__mro__[:3])
    print("PROBE FlagNoThreading set:", bool(flags & QgsProcessingAlgorithm.Flag.FlagNoThreading),
          "FlagCanCancel:", bool(flags & QgsProcessingAlgorithm.Flag.FlagCanCancel))
    print("PROBE group", alg.group(), "provider", alg.provider().id() if alg.provider() else None)
    sys.exit(0)

for i in range(repeats):
    t0 = time.monotonic()
    if variant == "sync":
        res = processing.run("gdal:slope", params(i), context=make_context())
        outcome = f"ok={os.path.exists(res['OUTPUT'])}"
    elif variant == "bg_current":
        from cartogen_ai.core.agent.tools import _background_processing as bg
        res = bg.run_algorithm("gdal:slope", params(i), make_context(),
                               fallback=lambda a, p, context=None: processing.run(a, p, context=context))
        outcome = f"ok={os.path.exists(res['OUTPUT'])}"
    elif variant in ("bg_cpp_feedback", "bg_poll", "bg_keepalive"):
        st = run_task(i, QgsProcessingFeedback(), "poll" if variant == "bg_poll" else "loop", keep=(variant == "bg_keepalive"))
        outcome = f"ok={st['ok']} done={st['done']}"
    else:
        print("PROBE unknown variant", variant)
        sys.exit(2)
    print(f"PROBE {variant} gui={gui} iteration {i} {outcome} {time.monotonic() - t0:.2f}s", flush=True)

print(f"PROBE {variant} gui={gui} finished {repeats} iterations", flush=True)
# Leave through the normal shutdown path: the earlier CI crash may have been at exit, not during the run.
app.exitQgis()
print("PROBE exitQgis returned", flush=True)
