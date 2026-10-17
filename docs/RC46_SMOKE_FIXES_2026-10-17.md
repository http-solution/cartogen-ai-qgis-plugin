# rc46: what the rc45 smoke run found, what was changed, and how far each change is checked (2026-10-17)

Source: the filled results of the rc45 hand-test sheet (an AI agent drove QGIS 4.2.3 on Windows with the plugin using Gemini; see
`docs/RC44_STATUS_AND_API_REVIEW_2026-10-16.md` for the sheet). 83 tool rows: 56 Pass, 22 Partial, 1 Fail, 4 Skip. 385 algorithm rows: 311 Pass,
54 Partial, 18 Fail, 2 Skip. Part 4 integration checks: 2 Pass, 5 Partial, 2 Fail, 1 Skip. The four rc44 bugs fixed in rc45 all passed.

Evidence levels used below: **offline** = plain unit tests in CI; **CI-live** = a test in a real QGIS 4.2.2 container (new tests are written
without a QGIS install, so their first CI run is their first execution); **not verified** = needs a desktop session.

## 1. Requests answered by the wrong task, or not reaching an algorithm at all
Cause. Two separate things.
- Nine rows were requests that spelled an algorithm's name and id ("Run the algorithm "v.type" (grass:v.type)"). One word of the name was also a
  word of an unrelated task in the task library (OpenStreetMap mapping, bridge damage, remote-sensing change detection), which answered with a
  confirm card.
- More important, and the point the owner raised: a real user does not spell the name. The only ways to reach an algorithm were a curated alias
  phrase per algorithm in the router and `find_processing_algorithm`, which needed every query word to appear in the algorithm's id or display
  name. GRASS names are "r.fillnulls", "v.net.bridge". "Fill the gaps in my elevation raster" found nothing.

Changes.
- New topic index (`core/agent/algorithm_topics.py` + `algorithm_topics.json`, built by `tools/build_algorithm_topics.py`): for each of the 427
  approved algorithms, word stems of its name and of its purpose (from the QGIS 4.2.3 Processing reference; hand-written phrases in
  `tools/algorithm_topic_notes.py` for the 164 the reference does not describe, mainly GRASS). Only stems are stored.
- The router now offers `find_processing_algorithm` and `run_allowlisted_processing_algorithm` when a request describes something an algorithm
  does, or when the request matches a register task that names algorithms. `find_processing_algorithm` uses the index when its strict search finds
  too little.
- A request that names an algorithm (id, or "algorithm" plus a quoted display name) gets no task directive. A request for a computation that
  matched a task whose tools only load and style data gets none either. A request for a chart is no longer answered by a map task.
- 37 register tasks (flood, drainage, terrain, density, hotspots, catchments, nearest facility, interpolation, duplicates, watershed, fire) now
  name the approved algorithms that fit, in `task_algorithms.json`; the directive lists up to three within its character budget.

Evidence. Offline: 30 plain-language requests (no algorithm names) each find their algorithm, or an equivalent one, in the first five results
and are offered the Processing tools (`tests/test_algorithm_topics.py`). On a separate set of 40 requests written during development the correct
algorithm was first for 20 and in the first five for 35. The wording of the requests was chosen by the author of the index, so this overstates
how a stranger would phrase them. **Not verified:** which algorithm a real model picks from the offered ones, and the effect on a live chat.

## 2. Undo
Cause. `undo_last_operation` only reached back into the same turn (a deliberate rule in `models/transactions.py`), so "undo the last operation"
typed as the next message found nothing. `delete_features` had no snapshot at all. `set_rule_based_labels` had no way to remove labels, so the
model called it with an empty list and got an error.
Changes. Undoable entries from the last five messages (at most ten) are kept; a project switch clears them; the confirm card says the change is
from an earlier message. `delete_features` snapshots the features about to go (up to 5,000) and puts them back as new features.
`set_rule_based_labels(clear=true)` removes the labels. This reverses a design decision, so the old test that asserted the opposite was rewritten.
Evidence. Offline: the log's carry-over rules (`tests/test_transactions.py`). CI-live (first run): delete and restore, labels cleared.

## 3. Stalls and freezes
Findings.
- The line "working on the road network..." was shown for every background algorithm, including raster ones. It is the plugin's own text (it was
  reported as "cloud network"). So the five stalled rows (`cellstackpercentile`, `cellstackpercentrankfromrasterlayer`,
  `cellstackpercentrankfromvalue`, `reclassifybylayer`, `detectvectorchanges`) were algorithms running in a worker thread, not a model stall.
  CI runs the same algorithms in seconds. **The cause is not found.** One plausible cause: a layer of the wrong kind handed to a parameter
  (CI already found that vectors in a raster stack crash QGIS; the smoke prompt gave a raster as the reclassification table).
- GRASS algorithms ran on the GUI thread and took 2 to 12 minutes each on Windows (v.voronoi 12, r.fillnulls 12, v.net.iso 8), also on tiny data.
  Linux CI runs the same ones in seconds, so the time is GRASS start-up on that machine, which this does not shorten.
- `grass:r.stream.extract`: QGIS closed during the run. Not reproduced in CI; left on the list, recorded here.
Changes. The status text no longer says "road network". A background algorithm now stops by itself after 300 s with a clear message
("ran longer than 300 seconds and was stopped; nothing was added"). Every layer parameter of every algorithm is checked for the right kind of
layer before running, not only raster stacks. GRASS and other GUI-thread algorithms run with a feedback object that lets Qt repaint every
0.25 s (user input is excluded), so the window stops showing "Not Responding". A "started" line is logged, so a future hang shows as a start
with no end in the Cartogen AI log tab.
Evidence. Offline: timeout wording, the layer-kind check with fake layer classes. CI-live (first run): a raster as a table is refused, a vector in a
stack is refused, a GRASS algorithm still runs. **Not verified:** that the 300 s limit fires (no safe test), that repainting works in a desktop
session, that the wrong-kind check is the cause of the five stalls. Stop still cannot interrupt a GRASS run on the GUI thread.

## 4. Smaller defects
- Overview map came out 42 mm high instead of 40: `setExtent` resized the item; now `zoomToExtent`.
- "Snapping to vertices and segments" set vertex only: it is two flags combined, not one type.
- Layout "Test Layout" was not found when the layout was called "Layout_Test_Layout": a loose-name lookup (case, spaces, underscores, a leading
  "Layout"; only when exactly one layout fits) is now used by every layout tool.
- Asked for `dem > 100` as a layer, the model tried `gdal:rastercalculator`, was refused and told the user to use the menu: the refusal now
  names the screened `raster_calculator` tool.
- "Values below 0 as no data" included 0: the range is inclusive; the tool description now says so.
- Multi-output algorithms (for example `grass:r.slope.aspect`) styled only their first output; every output is now styled.
- Not changed, by design: saving a second time to a file this session wrote itself does not ask again (the sheet expected a question).

## 5. Not done
- The hand-test sheet still names algorithms in its prompts. A version with plain-language prompts for the algorithm rows is the right next test
  of section 1, and has not been written.
- No pre-built chains for the new tools; GPS, PDAL algorithms and the 3D map layout item are still not built.
- Mesh and point-cloud rows were skipped for lack of fixtures.
