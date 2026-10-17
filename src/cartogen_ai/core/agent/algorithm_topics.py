"""Topic index for the approved Processing algorithms: find an algorithm from what a person WANTS, not from its name.

Why this exists. The approved list has 427 algorithms and most have names nobody types ("r.fillnulls", "Cell stack percentile",
"v.net.bridge"). Before rc46 the only ways to reach one were a curated alias phrase per algorithm in the tool router and
`find_processing_algorithm`, which required every word of its query to appear in the algorithm's id or display name. A request such as
"fill the gaps in my elevation raster" therefore found nothing, and the rc45 smoke run could only run algorithms whose test prompt
spelled the algorithm's own name and id.

The index (`algorithm_topics.json`, built by tools/build_algorithm_topics.py) holds, per algorithm, the stems of its display-name words
and of the words in its plain-English purpose (keywords from the QGIS 4.2.3 Processing reference, plus hand-written phrases for the
GRASS and a few other algorithms the reference does not describe). Only word stems are stored, not the reference's sentences.

Qt-free and QGIS-free, like task_matcher.py, so the router, the task matcher and the tool can all use it and the plain test suite can
check it. Nothing here raises: a missing or unreadable index means "no match", which is today's behaviour.
"""
import contextlib
import json
import math
import os
import re

_PATH = os.path.join(os.path.dirname(__file__), "algorithm_topics.json")
_WORD = re.compile(r"[a-z][a-z0-9]{2,}")

# Words that carry no topic: ordinary request wording and the vocabulary every GIS request shares.
_STOP = frozenset(["the", "and", "for", "with", "that", "this", "from", "into", "onto", "over", "under", "using", "use", "used", "make", "made", "build", "create", "generate", "add", "run", "show", "give", "please", "can", "you", "need", "want", "would", "like", "how", "what", "which", "where", "when", "your", "their", "its", "are", "was", "were", "been", "being", "have", "has", "had", "does", "did", "not", "all", "any", "some", "each", "per", "layer", "layers", "map", "maps", "data", "dataset", "file", "files", "value", "values", "new", "existing", "input", "output", "result", "results", "feature", "features", "cell", "cells", "my", "our", "algorithm", "tool", "tools", "algorithms", "processing", "grass", "qgis", "native", "gdal", "one", "two", "between", "through", "within", "also", "then", "than", "only", "more", "most", "other", "such", "get", "got", "put", "set", "take", "takes", "taking", "find", "calculate", "compute", "tell", "about", "around", "across", "along", "over", "near", "out", "off"])

# What users say, mapped to what the references say. Applied to the query AND to the index text, so both sides agree.
SYNONYMS = {
    "gap": "fill", "gaps": "fill", "hole": "fill", "holes": "fill", "missing": "fill", "empty": "fill", "void": "fill",
    "elevation": "elevation", "terrain": "elevation", "dem": "elevation", "height": "elevation", "heights": "elevation",
    "slope": "slope", "steep": "slope", "steepness": "slope",
    "river": "stream", "rivers": "stream", "creek": "stream", "drainage": "stream",
    "catchment": "watershed", "catchments": "watershed", "basin": "watershed", "basins": "watershed",
    "road": "network", "roads": "network", "street": "network", "streets": "network",
    "smooth": "smooth", "smoothing": "smooth", "simplify": "generalize", "simplification": "generalize",
    "hotspot": "density", "hotspots": "density", "heatmap": "density", "concentration": "density",
    "resolution": "resample", "coarser": "resample", "finer": "resample", "regrid": "resample",
    "reproject": "reproject", "transform": "reproject",
    "sun": "solar", "sunlight": "solar", "shade": "solar", "shadow": "solar", "shadows": "solar",
    "visible": "viewshed", "visibility": "viewshed", "lineofsight": "viewshed",
    "erosion": "erosion", "wildfire": "fire", "burn": "fire",
    "interpolate": "interpolation", "interpolating": "interpolation",
    "polygon": "polygon", "polygons": "polygon",
    "randomly": "random", "sample": "random", "sampling": "random",
    "percentile": "percentile",
    "central": "centrality", "important": "importance", "junction": "node", "junctions": "node", "intersections": "node",
    "cluster": "cluster", "clusters": "cluster", "clustering": "cluster",
    "outline": "hull", "footprint": "hull",
}


def stem(word):
    """Light suffix stripping so 'fills' / 'filling' / 'filled' meet. Deterministic; applied to both sides."""
    w = word
    for suf in ("ing", "ied", "ies", "ed", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            w = w[: -len(suf)] + ("y" if suf in ("ied", "ies") else "")
            break
    return w


def tokenize(text, synonyms=False):
    """Ordered stems of the topic words in `text`. Pure."""
    out = []
    for raw in _WORD.findall((text or "").lower().replace("_", " ").replace(".", " ")):
        if raw in _STOP:
            continue
        s = stem(SYNONYMS.get(raw, raw) if synonyms else raw)
        if s not in _STOP and len(s) > 2:
            out.append(s)
    return out


_INDEX = {}
_IDF = {}
_LOADED: list[bool] = []


def _load():
    if not _LOADED:
        _LOADED.append(True)
        with contextlib.suppress(Exception), open(_PATH, encoding="utf-8") as fh:
            _INDEX.update(json.load(fh))
        _IDF.update(_idf_of(_INDEX))
    return _INDEX

_NAME_BONUS = 2.0
# A match needs this much evidence. One ordinary shared word ("raster") is not a topic.
MIN_SCORE = 5.5
MIN_DISTINCT = 2


def rank(query, limit=8, index=None):
    """[(algorithm_id, score, matched_stems)] best first, only those with enough evidence. Pure given the index."""
    idx = _load() if index is None else index
    q = list(dict.fromkeys(tokenize(query, synonyms=True)))
    if not q or not idx:
        return []
    idf = _IDF if index is None else _idf_of(idx)
    scored = []
    for alg_id, entry in idx.items():
        names, keys = set(entry.get("n", [])), set(entry.get("k", []))
        hits = [s for s in q if s in names or s in keys]
        if len(hits) < MIN_DISTINCT and not any(s in names and idf.get(s, 0) >= 3.0 for s in hits):
            continue
        score = sum(idf.get(s, 1.0) * (_NAME_BONUS if s in names else 1.0) for s in hits)
        if alg_id.startswith("grass:"):
            score *= 0.9        # GRASS needs its own install; prefer an equally good native, GDAL or QGIS algorithm
        if score >= MIN_SCORE:
            scored.append((alg_id, round(score, 3), hits))
    scored.sort(key=lambda x: (-x[1], x[0]))
    return scored[:limit]


def _idf_of(idx):
    n = max(len(idx), 1)
    df = {}
    for entry in idx.values():
        for s in set(entry.get("n", [])) | set(entry.get("k", [])):
            df[s] = df.get(s, 0) + 1
    return {s: math.log(1 + n / c) for s, c in df.items()}


def best_for(query):
    """The single best (id, score, hits) for a request, or None. Used where one answer is enough."""
    r = rank(query, limit=1)
    return r[0] if r else None


# provider:name ids as people paste them ("native:buffer", "grass:r.fillnulls")
_ID_IN_TEXT = re.compile(r"\b(?:native|qgis|gdal|grass|3d|pdal):[a-z0-9_.]+", re.IGNORECASE)


def named_algorithm_ids(query):
    """Approved algorithm ids the request spells out. A request that names an algorithm has said what to run (like a named tool)."""
    found = {m.lower() for m in _ID_IN_TEXT.findall(query or "")}
    if not found:
        return set()
    with contextlib.suppress(Exception):
        from .tools._processing_allowlist import ALLOWED_ALGORITHM_IDS
        return found & set(ALLOWED_ALGORITHM_IDS)
    return found


_QUOTED = re.compile(r"[\"'\u201c\u2018]([^\"'\u201d\u2019]{3,80})[\"'\u201d\u2019]")


def names_algorithm(query):
    """True when the request itself says which Processing algorithm to run: it spells an approved id ("native:buffer"), or it says
    "algorithm" and quotes an approved display name ('Run the algorithm "Add geometry attributes"'). rc45 smoke run: nine such requests
    were answered with a task-library confirm card for an unrelated task (OpenStreetMap mapping, bridge damage, remote-sensing change
    detection) because a word of the algorithm's name was also a word of that task. Like a named tool, a named algorithm has already
    said what to run, so no task directive should compete with it. Pure."""
    if named_algorithm_ids(query):
        return True
    text = query or ""
    if not re.search(r"\balgorithms?\b", text, re.IGNORECASE):
        return False
    quoted = {q.strip().lower() for q in _QUOTED.findall(text)}
    if not quoted:
        return False
    with contextlib.suppress(Exception):
        from .tools._processing_allowlist import FAMILY_NAMES
        return bool(quoted & {str(n).lower() for n in FAMILY_NAMES.values()})
    return False


# A request with an analysis verb plus strong algorithm evidence is asking for a computation, not for existing data to be shown.
ANALYSIS_VERBS = re.compile(
    r"\b(calculat\w*|comput\w*|creat\w*|generat\w*|deriv\w*|extract\w*|delineat\w*|fill\w*|interpolat\w*|simulat\w*|run|"
    r"find|identif\w*|convert\w*|reclassif\w*|resampl\w*|reproject\w*|rasteri[sz]\w*|vectori[sz]\w*|cluster\w*|dissolv\w*|"
    r"smooth\w*|simplif\w*|merg\w*|union|intersect\w*)\b", re.IGNORECASE)
STRONG_SCORE = 9.0
# Tasks whose tools only load and style existing data: they cannot do the computation the request asks for.
DISPLAY_ONLY_TOOLS = frozenset({"add_layer_from_path", "apply_categorized_style", "apply_graduated_style", "zoom_to_layer",
                                "add_basemap", "get_layers", "style_layer", "apply_single_style"})


def computation_request(query, task_tools=()):
    """True when the request asks for a computation an approved algorithm can do AND the task it matched can only show data. Pure."""
    tools = set(task_tools or ())
    if not tools or not tools <= DISPLAY_ONLY_TOOLS or not ANALYSIS_VERBS.search(query or ""):
        return False
    top = best_for(query)
    return bool(top and top[1] >= STRONG_SCORE)
