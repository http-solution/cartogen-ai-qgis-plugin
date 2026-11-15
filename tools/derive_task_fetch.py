"""Put a data-fetch tool first in the tool order of the 'Map ...' tasks of the task register (TR-1), in place.

Why (owner's Taiz run, 2026-11-01): 279 of the 302 'Map ...' tasks began their "Prefer these tools, in order: ..." line with
add_layer_from_path, which loads a FILE the user already has. The model was told to start there for "map hospitals and clinics" and never
fetched anything. 1.02, 1.05 and the hand-fixed 6.02 start with fetch_osm_features; this script does the same for every task whose subject
is a physical feature OpenStreetMap carries, and points data-themed tasks (disease, hazards, conflict, food security, climate) at
search_hdx_datasets. A task that fits no rule is left alone on purpose: no fetch tool honestly fits it (--stats lists them).

Only the "tools" key changes, and only by inserting ONE tool at the front; nothing is ever removed or reordered. A task that already has
any fetch/ingest/search tool is skipped.

Run:  python tools/derive_task_fetch.py            # rewrite the register
      python tools/derive_task_fetch.py --check    # exit 1 if it would change
      python tools/derive_task_fetch.py --stats    # what matched and what did not

tests/test_task_fetch_tools.py re-runs the derivation against the committed register, so a rule change shows up as a diff."""
import argparse
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REGISTER = os.path.join(ROOT, "src", "cartogen_ai", "core", "agent", "task_register.json")

FETCH_PREFIXES = ("fetch_", "ingest_", "search_hdx")

# What OpenStreetMap does not carry and a map of it would be an assessment: damage, status, capacity, coverage, gaps.
_NOT_OSM = re.compile(r"damage|affected|inaccessible|relocated|closed|operating|opening hours|capacity|coverage|gaps|catchment|"
                      r"availability|trends|travel times|constraints|restrictions|needs|incidents|cases|quality|contamination|prices", re.I)

# (pattern over the text after 'Map ', tool). First match wins, so the specific rules come first.
_RULES = [
    (re.compile(r"burned areas", re.I), "fetch_nasa_active_fires"),
    (re.compile(r"disaster-affected areas|cyclone, hurricane, and storm impacts", re.I), "fetch_gdacs_disaster_alerts"),
    (re.compile(r"age and sex distribution", re.I), "fetch_worldpop_population"),
    # physical features OpenStreetMap carries (skipped when the text is an assessment of them, see _NOT_OSM)
    (re.compile(
        r"health facilities|health posts|pharmac|laborator|schools|learning centers|temporary learning|water sources|water points|"
        r"boreholes|wells\b|water-treatment|treatment facilities|pipelines|storage tanks|latrine|toilets|bathing|handwashing|"
        r"waste-collection|waste-disposal|solid-waste|markets|shops|shelters|accommodation|community centers|community spaces|"
        r"warehouses|distribution (centers|points)|food-distribution|transport terminals|ports, airports|fuel stations|electricity|"
        r"telecommunications|lighting|government offices|partner offices|checkpoints|settlements|rivers|lakes|coastlines|drainage|"
        r"place names|immunization sites|nutrition (facilities|treatment centers)|treatment centers|helicopter|communal facilities|"
        r"firebreaks|evacuation routes|access routes|supply routes|vehicle routes|collective centers|businesses|protected areas|"
        r"wetlands|facilities and services|community assets|camp blocks", re.I), "fetch_osm_features"),
    # data-themed subjects with no OpenStreetMap layer: look for a published dataset
    (re.compile(
        r"disease|outbreak|cholera|mortality|vaccination|malnutrition|food-insecure|food-consumption|food prices|food-assistance|"
        r"conflict|armed-group|attacks|front lines|territorial|explosi|landmines|protection incidents|curfews|"
        r"flood|drought|earthquake|landslide|volcanic|tsunami|extreme-heat|cold-weather|avalanche|erosion|coastal hazards|"
        r"climate|rainfall|temperature|soil moisture|vegetation|land degradation|deforestation|desertification|air pollution|"
        r"agricultural|crop|pasture|fishing|economic activity|employment|livelihood|priority needs|assistance coverage|"
        r"households|enrollment|land use|elevation|hazard", re.I), "search_hdx_datasets"),
]


def fetch_tool_for(entry):
    """The fetch tool to put first for this task, or None (not a 'Map ...' task, already has one, or no honest fit). Pure."""
    text = entry.get("text", "")
    if not text.lower().startswith("map ") or any(t.startswith(FETCH_PREFIXES) for t in entry.get("tools", [])):
        return None
    subject = text[4:]
    for pattern, tool in _RULES:
        if pattern.search(subject):
            if tool == "fetch_osm_features" and _NOT_OSM.search(subject):
                continue
            return tool
    return None


def derive(entries):
    out = []
    for e in entries:
        n = dict(e)
        tool = fetch_tool_for(e)
        if tool:
            n["tools"] = [tool, *e["tools"]]
        out.append(n)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="exit 1 if the committed register differs from the derivation")
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args()
    with open(REGISTER, encoding="utf-8") as fh:
        data = json.load(fh)
    new = derive(data)
    if args.stats:
        import collections
        added = collections.Counter(n["tools"][0] for o, n in zip(data, new, strict=True) if o != n)
        maps = [e for e in new if e["text"].lower().startswith("map ")]
        left = [e for e in maps if not any(t.startswith(FETCH_PREFIXES) for t in e["tools"])]
        print(f"'Map ...' tasks: {len(maps)}   still without a fetch tool: {len(left)}   to change now: {sum(added.values())}")
        print("added:", dict(added))
        for e in left:
            print(f"  {e['id']:7} {e['text']}")
        return 0
    if args.check:
        if data == new:
            print(f"register fetch tools are up to date ({len(new)} tasks)")
            return 0
        diff = [n["id"] for o, n in zip(data, new, strict=True) if o != n]
        print(f"register is STALE -- {len(diff)} task(s) would change, e.g. {diff[:10]}")
        return 1
    with open(REGISTER, "w", encoding="utf-8") as fh:
        json.dump(new, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {REGISTER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
