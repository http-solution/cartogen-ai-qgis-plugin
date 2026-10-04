# -*- coding: utf-8 -*-
"""Which Processing algorithm ids the source references. Pure (no QGIS), shared by the offline test and the live registry diagnostic."""
import os
import re

_ID = re.compile(r'''["']((?:native|gdal|qgis|saga|grass7?|pdal|3d):[a-zA-Z0-9_]+)["']''')
_SRC = os.path.join(os.path.dirname(__file__), "..", "src", "cartogen_ai")


def referenced_algorithm_ids(root=_SRC):
    """{id: sorted list of files (relative to the package) that mention it}. Counts every string literal that looks like an
    algorithm id, including ids in comments' quoted examples, so it may over-report; a test or a person reads the list."""
    found = {}
    for folder, _dirs, files in os.walk(root):
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(folder, name)
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            for match in _ID.finditer(text):
                found.setdefault(match.group(1), set()).add(os.path.relpath(path, root).replace(os.sep, "/"))
    return {k: sorted(v) for k, v in sorted(found.items())}


def suggestions(missing_id, all_ids, limit=6):
    """Registry ids that might be what `missing_id` became: same short name under another provider first, then ids whose short
    name contains the first word of the missing one. Pure."""
    short = missing_id.split(":", 1)[1]
    same = [a for a in all_ids if a.split(":", 1)[1] == short and a != missing_id]
    stem = re.split(r"(?<=[a-z])(?=[A-Z])|_", short)[0][:8]
    near = [a for a in all_ids if a not in same and a != missing_id and stem and stem in a.split(":", 1)[1].lower()]
    return (same + sorted(near))[:limit]
