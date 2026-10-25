"""Model-free layout check for a hand test (PLAN-021 WP-G). Runs in the QGIS Python console, makes NO model calls (so no API cost) and builds its own
project, so no check depends on another or on what is open.

In the QGIS Python console (the plugin must be installed and enabled):

    exec(open(r"C:\\path\\to\\layout_check_script.py", encoding="utf-8").read())

It writes, into a new folder beside the script (or the folder given to run()):
  layout_check.json   one entry per check: id, what was expected, what was measured, pass/fail
  layout_check.txt    the same as a table, plus the plugin version and the fonts QGIS found
  *.pdf, *.png        every layout it built, exported, to look at
and prints the table. Send the whole folder back.

What it does NOT replace: whether a page looks right to a person. It measures (legend content against its frame, footer height against its
box and the page, names, refusals, file names, dpi) and exports the pages; the pages are for the eye.

Written without a QGIS install at hand: tests/test_layout_check_script_live.py runs run() in the CI live job, so the script is proven there
before anyone runs it on a real machine. Not proven there: the owner's Windows fonts, which is the point of running it on that machine.
"""
import contextlib
import datetime
import json
import os
import tempfile
import time
import traceback
from unittest.mock import patch

FULL_SIGN_OFF = {"prepared_by": "Tester", "reviewed_by": "Reviewer Test", "review_date": "2026-10-25", "status": "Reviewed"}
OSM_URI = "type=xyz&url=https://tile.openstreetmap.org/%7Bz%7D/%7Bx%7D/%7By%7D.png&zmax=19&zmin=0"
DISCLAIMER_START = "Boundaries, names, and designations"
DISCLAIMER_END = "external distribution."


def run(output_dir=None, quiet=False):  # noqa: C901 -- one flat list of independent checks; splitting it would hide that
    """Runs every check; returns the list of results (also written to layout_check.json). Never raises: a check that fails is reported as failed."""
    from qgis.core import (Qgis, QgsCategorizedSymbolRenderer, QgsFeature, QgsGeometry, QgsProject, QgsRasterLayer,
                           QgsRendererCategory, QgsSymbol, QgsVectorLayer)
    from qgis.PyQt.QtGui import QColor, QImage

    started = time.time()
    out = output_dir or os.path.join(tempfile.gettempdir(), "cartogen_layout_check_" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    os.makedirs(out, exist_ok=True)
    profiles = os.path.join(out, "cartogen_profiles")
    os.makedirs(profiles, exist_ok=True)
    results = []

    def record(check_id, title, expect, fn):
        entry = {"id": check_id, "title": title, "expect": expect, "ok": False, "got": {}, "files": []}
        try:
            ok, got, files = fn()
            entry.update(ok=bool(ok), got=got, files=[os.path.basename(f) for f in files if f])
        except Exception as exc:                                    # a check that cannot run is a failed check, with the reason
            entry.update(ok=False, got={"error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc(limit=4)})
        results.append(entry)

    def reset_project():
        QgsProject.instance().clear()
        QgsProject.instance().setFileName(os.path.join(out, "layout_check.qgz"))     # so project-relative folders (profiles) resolve here

    def zones(name, categories, x0=43.9):
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=kind:string", name, "memory")
        feats = []
        for i in range(categories):
            f = QgsFeature(layer.fields())
            x = x0 + 0.01 * i
            f.setGeometry(QgsGeometry.fromWkt(f"POLYGON(({x} 14.9,{x + 0.009} 14.9,{x + 0.009} 15.0,{x} 15.0,{x} 14.9))"))
            f.setAttributes([f"class {i}"])
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        layer.updateExtents()
        cats = []
        for i in range(categories):
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            symbol.setColor(QColor.fromHsv((i * 29) % 360, 160, 220))
            cats.append(QgsRendererCategory(f"class {i}", symbol, f"class {i}"))
        layer.setRenderer(QgsCategorizedSymbolRenderer("kind", cats))
        QgsProject.instance().addMapLayer(layer)
        return layer

    def points(name="clinics"):
        layer = QgsVectorLayer("Point?crs=EPSG:4326&field=val:double", name, "memory")
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt("POINT(44 15)"))
        f.setAttributes([1.0])
        layer.dataProvider().addFeatures([f])
        layer.updateExtents()
        QgsProject.instance().addMapLayer(layer)
        return layer

    def write_profile(name, body):
        with open(os.path.join(profiles, name + ".json"), "w", encoding="utf-8") as handle:
            json.dump(body, handle)

    def layout_of(res):
        return QgsProject.instance().layoutManager().layoutByName(res["layout_name"])

    def export(res, name, ext="pdf", **kw):
        from cartogen_ai.core.agent.tools.layout_item_tools import export_layout
        path = os.path.join(out, f"{name}.{ext}")
        return export_layout(res["layout_name"], path, confirmed=True, **kw), path

    def make(title, **kw):
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        res = create_print_layout(title, confirmed=True, body_text="Finding", **kw)
        if not res.get("success"):
            raise RuntimeError(f"create_print_layout failed: {res}")
        return res

    def footer_numbers(res):
        check = res.get("footer_check") or {}
        return {"footer_check": check, "footer_warnings": [w for w in res.get("style_warnings", []) if "footer" in w]}

    with patch("cartogen_ai.core.agent.tools.map_profiles.profile_dirs", lambda: [profiles]):
        # ---- L1 legend: many layers with many classes, both page shapes
        for size, orientation in (("A4", "Landscape"), ("A3", "Portrait")):
            def legend_check(size=size, orientation=orientation):
                reset_project()
                for n in range(7):
                    zones(f"zones_{n}", 14)
                res = make(f"Legend {size}", page_size=size, page_orientation=orientation)
                check = res.get("legend_check") or {}
                title = layout_of(res).itemById("LEGEND").title()
                _, pdf = export(res, f"legend_{size}_{orientation}")
                ok = bool(check) and check.get("fits") is True and check.get("content_mm", 1e9) <= check.get("frame_mm", 0) + 0.5
                if check.get("dropped"):
                    ok = ok and "more layer" in title
                return ok, {"legend_check": check, "legend_title": title, "listed": len(res.get("legend_layers", []))}, [pdf]
            record(f"L1-{size}", f"legend fits its frame ({size} {orientation}, 7 layers x 14 classes)",
                   "content height not larger than the frame; if layers were left out the title says how many", legend_check)

        # ---- L2 footer and disclaimer, default wording
        def footer_default():
            reset_project()
            points()
            res = make("Footer Test")
            text = layout_of(res).itemById("FOOTER").text()
            exported, pdf = export(res, "footer_default")
            numbers = footer_numbers(res)
            check = numbers["footer_check"]
            ok = (check.get("fits") is True and check.get("bottom_mm", 1e9) <= check.get("page_mm", 0)
                  and not numbers["footer_warnings"] and "AI-generated" in text and "Sources:" in text
                  and DISCLAIMER_START in text and text.rstrip().endswith(DISCLAIMER_END) and exported.get("success"))
            return ok, {**numbers, "footer_lines": len(text.split("\n")), "export": bool(exported.get("success"))}, [pdf]
        record("L2", "footer: AI note, sources, disclaimer, fits the page, no warning", "footer_check.fits and no footer warning; text complete", footer_default)

        # ---- L3 credits for an OpenStreetMap basemap
        def credits_osm():
            reset_project()
            points()
            basemap = QgsRasterLayer(OSM_URI, "OpenStreetMap", "wms")
            QgsProject.instance().addMapLayer(basemap)
            res = make("Credit Test")
            text = layout_of(res).itemById("FOOTER").text()
            wanted = "Credits: Basemap: OpenStreetMap contributors (ODbL)"
            numbers = footer_numbers(res)
            return text.count(wanted) == 1 and not numbers["footer_warnings"], {**numbers, "credits_found": text.count(wanted)}, []
        record("L3", "credits line names OpenStreetMap contributors (ODbL) once", "exactly one credits line, no footer warning", credits_osm)

        # ---- L4 A3 landscape, name kept, no geometry problem
        def big_map():
            reset_project()
            points()
            res = make("Big Map", page_size="A3", page_orientation="Landscape")
            exported, pdf = export(res, "big_map_A3")
            page = layout_of(res).pageCollection().page(0).pageSize()
            ok = res["layout_name"] == "Big Map" and exported.get("success") and not exported.get("layout_problems") and round(page.width()) == 420
            return ok, {"layout_name": res["layout_name"], "page_mm": [round(page.width()), round(page.height())],
                        "layout_problems": exported.get("layout_problems", [])}, [pdf]
        record("L4", "A3 landscape layout keeps the name 'Big Map', nothing overlaps or is cut off", "name 'Big Map', 420 mm wide, no layout problems", big_map)

        # ---- L5 export preset and file name
        def preset_name():
            reset_project()
            points()
            folder = os.path.join(out, "preset")
            os.makedirs(folder, exist_ok=True)
            from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
            res = create_print_layout("Name check", output_path=folder, output_format="png", preset="web", confirmed=True)
            expected = os.path.join(folder, f"Name check_{datetime.date.today().isoformat()}.png")
            ok = res.get("success") and res.get("dpi") == 150 and os.path.isfile(expected)
            return ok, {"dpi": res.get("dpi"), "file": os.path.basename(res.get("output_path", "")), "expected_file": os.path.basename(expected)}, [expected]
        record("L5", "web preset exports at 150 dpi, named from the title and today's date", "dpi 150; file '<title>_<date>.png'", preset_name)

        # ---- L6 profile: page, masthead, footer lines, sign-off line
        def profile_layout():
            reset_project()
            points()
            write_profile("handtest", {"page_size": "A3", "orientation": "portrait", "masthead_colour": "#2b5d8a",
                                       "footer_lines": ["Contact: test@example.org", "Footer line 2", "Footer line 3"],
                                       "sign_off": {"prepared_by": "Tester"}})
            res = make("Profile Test", profile="handtest")
            layout = layout_of(res)
            text = layout.itemById("FOOTER").text()
            page = layout.pageCollection().page(0).pageSize()
            exported, pdf = export(res, "profile_test")
            numbers = footer_numbers(res)
            ok = (round(page.width()) == 297 and round(page.height()) == 420 and "Contact: test@example.org" in text
                  and "Prepared by Tester | Status: Draft - not reviewed" in text and not numbers["footer_warnings"]
                  and numbers["footer_check"].get("fits") is True and exported.get("success"))
            return ok, {**numbers, "page_mm": [round(page.width()), round(page.height())]}, [pdf]
        record("L6", "profile: A3 portrait, blue masthead, three footer lines, draft sign-off line, footer fits", "all present, no footer warning", profile_layout)

        # ---- L7 logo present, then missing
        def logo():
            reset_project()
            points()
            image = QImage(60, 30, QImage.Format.Format_RGB32)
            image.fill(QColor("#e8a317"))
            if not image.save(os.path.join(profiles, "mark.png")):
                raise RuntimeError("could not write the test logo")
            write_profile("logo", {"logo_path": "mark.png", "masthead_colour": "#2b5d8a"})
            res = make("Logo Test", profile="logo")
            layout = layout_of(res)
            item, title = layout.itemById("LOGO"), layout.itemById("TITLE")
            exported, pdf = export(res, "logo_test")
            present = item is not None and item.x() + item.rect().width() <= title.x() + 0.01
            os.rename(os.path.join(profiles, "mark.png"), os.path.join(profiles, "mark_moved.png"))
            res2 = make("Logo Missing Test", profile="logo")
            warned = any("logo" in w for w in res2.get("style_warnings", []))
            return present and warned and exported.get("success"), {"logo_left_of_title": present, "missing_logo_warned": warned,
                                                                 "missing_logo_layout_made": bool(res2.get("success"))}, [pdf]
        record("L7", "logo sits left of the title; a missing logo warns and the layout is still made", "present, no overlap; warning when missing", logo)

        # ---- L8 sign-off required, then given
        def sign_off():
            reset_project()
            points()
            write_profile("signed", {"require_sign_off": True, "sign_off": {"prepared_by": "Tester"}})
            res = make("Sign Off Test", profile="signed")
            from cartogen_ai.core.agent.tools.layout_item_tools import export_layout
            refused = export_layout(res["layout_name"], os.path.join(out, "refused.png"), purpose="publication")
            blocked = "error" in refused and any("sign-off" in p for p in refused.get("problems", [])) and not os.path.exists(os.path.join(out, "refused.png"))
            write_profile("signed2", {"require_sign_off": True, "sign_off": FULL_SIGN_OFF})
            res2 = make("Sign Off Given", profile="signed2")
            pdf = os.path.join(out, "signed.pdf")
            accepted = export_layout(res2["layout_name"], pdf, purpose="publication")
            return blocked and bool(accepted.get("success")), {"refused": blocked, "refusal_problems": refused.get("problems", []),
                                                               "accepted_with_review": bool(accepted.get("success"))}, [pdf]
        record("L8", "publication export is refused without a reviewer sign-off and accepted with one", "refused with 'sign-off'; accepted with review", sign_off)

        # ---- L9 profile edited after the layout was made
        def reread():
            reset_project()
            points()
            write_profile("reread", {"page_size": "A4", "sign_off": {"prepared_by": "Tester"}})
            res = make("Reread Test", profile="reread")
            write_profile("reread", {"page_size": "A4", "require_sign_off": True, "sign_off": {"prepared_by": "Tester"}})
            from cartogen_ai.core.agent.tools.layout_item_tools import export_layout
            refused = export_layout(res["layout_name"], os.path.join(out, "reread.png"), purpose="publication")
            blocked = "error" in refused and any("sign-off" in p for p in refused.get("problems", []))
            return blocked, {"refused_after_profile_change": blocked, "problems": refused.get("problems", [])}, []
        record("L9", "a requirement added to the profile after the layout was built still blocks publication", "refused", reread)

        # ---- L10 the full disclaimer, the Help section, the Settings wording
        def disclaimer():
            reset_project()
            points()
            res = make("Disclaimer Test")
            text = layout_of(res).itemById("FOOTER").text()
            exported, pdf = export(res, "disclaimer_test")
            from cartogen_ai.core.disclaimer_text import TERMS_TITLE
            from cartogen_ai.core.ui.help_content import build_help_html
            help_has = TERMS_TITLE in build_help_html()
            ok = DISCLAIMER_START in text and text.rstrip().endswith(DISCLAIMER_END) and help_has and exported.get("success")
            return ok, {**footer_numbers(res), "help_section_present": help_has}, [pdf]
        record("L10", "full disclaimer in the footer and the Help section 'Disclaimer and terms of use'", "both present", disclaimer)

    reset_project()
    fonts = []
    with contextlib.suppress(Exception):
        from qgis.PyQt.QtGui import QFontDatabase
        fonts = [f for f in ("Segoe UI", "Arial", "Calibri", "DejaVu Sans") if f in QFontDatabase.families()]
    version = ""
    with contextlib.suppress(Exception):
        meta = os.path.normpath(os.path.join(os.path.dirname(os.path.dirname(__import__("cartogen_ai").__file__)), "..", "metadata.txt"))
        with open(meta, encoding="utf-8") as handle:
            version = next((line.strip().split("=", 1)[1] for line in handle if line.startswith("version=")), "")
    summary = {"qgis": Qgis.version(), "plugin_version": version, "fonts_found": fonts, "folder": out, "seconds": round(time.time() - started, 1),
               "passed": sum(1 for r in results if r["ok"]), "failed": [r["id"] for r in results if not r["ok"]], "checks": results}
    with open(os.path.join(out, "layout_check.json"), "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, default=str)
    lines = [f"Cartogen AI layout check  QGIS {summary['qgis']}  plugin {version or '?'}  fonts: {', '.join(fonts) or 'none of the usual ones'}", ""]
    for r in results:
        lines.append(f"{'PASS' if r['ok'] else 'FAIL'}  {r['id']:7} {r['title']}")
        if not r["ok"]:
            lines.append(f"        expected: {r['expect']}")
            lines.append(f"        measured: {json.dumps(r['got'], default=str)[:600]}")
    lines += ["", f"{summary['passed']} of {len(results)} passed. Folder: {out}"]
    with open(os.path.join(out, "layout_check.txt"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    if not quiet:
        print("\n".join(lines))
    return summary


if __name__ == "__main__":
    run()
