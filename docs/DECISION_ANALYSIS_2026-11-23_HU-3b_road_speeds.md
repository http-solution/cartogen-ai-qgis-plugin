# Decision aid: what speed should a road get when the map has none? (HU-3 part b, 2026-11-23)

Written for the owner. Plain language. Nothing here changes code; it needs your choice first.

## What is true today (checked in the code)

- **The problem:** in a real Jordan road file only 1,504 of 161,041 roads (0.9 percent) carry a speed. A "fastest" route or a "within one hour" reach then gives every other road the same flat 50 km/h, so a motorway and a 30 km/h back street count the same.
- **It is disclosed, not hidden:** when no speed field is used the result says "a flat 50 km/h on every road" and calls the time a model estimate. If a speed field is supplied but nearly empty, the plugin ignores it, says so, and points to `estimate_road_speeds`.
- **A fix already exists, but it is opt-in:** `estimate_road_speeds` writes an `assumed_speed_kmh` field from a table by road class (motorway 100, trunk 80, primary 70, secondary 60, tertiary 50, residential 40, service and track 20). It can scale to a country's legal limits for 15 countries (AE, AT, AU, CA, CN, CZ, DE, EG, ES, FR, GB, HU, JO, SA, US; not Yemen). Its description tells the model never to call it automatically. It shows a preview card before writing to the layer.
- **A second, different table exists:** `build_composite_impedance_field` (road class plus surface and slope penalties) uses its own base speeds: primary 60, secondary 50, tertiary 40, residential 30, unclassified 30. For the main classes that is 10 km/h lower than the table above. Neither table has been checked against a known journey, and I cannot do that here.
- **Not measured:** I have not compared the flat-50 answer with a class-based answer on a real network, so I cannot say how much results would move.

## The choices

| Option | What happens | Honest about the assumption? | Risk |
|---|---|---|---|
| **A. Keep opt-in** (today) | Flat 50 km/h unless the model remembers to call `estimate_road_speeds` first. | Yes, the result says "flat 50". | A one-hour reach is still wrong on most real networks, and it depends on the model choosing to call the tool. |
| **B. Automatic fallback, in memory only** (recommended) | When the answer is "fastest" and there is no usable speed field but there is a road-class field, the tool uses the class table for that one run and writes nothing to your layer. The result states the assumption, the table used and the country scaling, if any. | Yes, in every result. | Changes numbers people may rely on (flat 50 becomes class-based). Needs one clear line in the release notes. |
| **C. Ask first with a card** | Same as B, but a card shows the table and you press Apply. | Yes, and you approve it. | More friction on every routing question; most users would just press Apply. |
| **D. Make the two tables one** (independent of A to C) | `estimate_road_speeds` and the composite impedance tool share one table. | n/a | Small. But it changes the composite tool's results by up to 10 km/h on main roads, and I do not know which table is right. |

## Recommendation

**B, together with D.** A flat 50 km/h everywhere is almost certainly further from the truth than a stated class table, and B keeps your layer untouched and says so in every result. On D, I would adopt the `estimate_road_speeds` table, because it is the one your 2026-09 bug entry named, and keep the composite tool's surface and slope penalties on top. If you prefer to stay cautious, A with a stronger warning, or C, are both fine; the cost is friction or wrong numbers, not harm.

What I would do after your go: implement it behind tests that show the result carries the assumption text, that your layer is not written to, and that a supplied speed field still wins. It would be CI-checked only and not hand-tested until a person compares it with a journey they know.

## What I need from you

One letter for **A, B, C or D** (B and D can be combined). Part (c), timing a whole-country matrix, still needs a country-sized network to profile and is not decided here.
