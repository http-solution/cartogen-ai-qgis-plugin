# Plain-language algorithm test (humanitarian GIS), 2026-10-17

**Why.** The first hand test (`HAND_TEST_SHEET_rc44_2026-10-16.md`) told the chat which algorithm to run, by name and id. A person does not do that.
This test gives only the job to be done, the way a field GIS officer would type it. It measures what the first one could not: whether the chat
FINDS the right Processing algorithm from a description, and whether the result is right.

**File.** `docs/HAND_TEST_rc46_algorithms_plain.csv`, 385 rows, one per algorithm of the earlier sheet (geometry 73, table 11, analysis 35, expression 5,
raster 66, mixed 35, GRASS 154, mesh 6). Run it on rc46 or later (the discovery changes are not in rc45).

**Fixtures.** The same as the first sheet's section 0: `districts` (4 polygons: name, pop), `towns` (8 points: name, pop), `roads` (lines), `dem` and
`dem2` (elevation rasters, dem2 has holes of no data), `mesh1` if it could be built. Prompts name these layers the way a user would ("the roads", "the
dem"). Rows that need data the fixtures do not have say so; the right behaviour there is a clear statement of what is missing, not an invented result.

## Rules
1. Type the **plain_prompt** exactly. Do not add the algorithm's name, id or family, and do not suggest which tool to use. If the chat asks which
   algorithm you mean, answer in plain words about the result you want.
2. Start each row in a fresh chat turn after clearing the previous request (a leftover confirm card or plan can contaminate the next row).
3. Fill four columns:
   - **chat_called**: the tool and the algorithm id the chat showed (for example `run_allowlisted_processing_algorithm / native:boundary`, or a dedicated tool).
   - **right_algorithm**: **Y** it ran the algorithm in the row, **equivalent** it ran another approved algorithm or a dedicated tool that gives the same
     answer (note which), **N** it ran something else or nothing.
   - **result**: **Pass** the output answers the request; **Partial** it ran but the result is wrong, ugly or incomplete (say how); **Fail** error, hang or
     wrong; **Skip** the data the row needs does not exist (say which).
   - **notes**: the message if it failed; how long it took if more than 30 seconds.
4. For a **Fail** or **Partial**, copy the exact prompt and the first reply.

## What to look for beyond pass or fail
- **Discovery.** Count how often the chat searches more than once before running (`find_processing_algorithm` calls) and how often it gives up and says
  there is no tool. Both mean the wording did not reach the algorithm. Write the wording that finally worked in notes: it is the best input for the next
  improvement of the search vocabulary.
- **A task card instead of the algorithm.** If the chat shows a "Recognised task" confirm card for a request that asked for a computation, mark it and
  note the task number. Cancel it and say "just run it"; do not accept it.
- **Time.** A native algorithm on this data should finish in seconds. A GRASS algorithm may take minutes on Windows (the window should keep painting);
  note the time. Anything past 5 minutes on a native algorithm should now stop itself with a message; record that.
- **Look.** Continuous raster results should open with a colour ramp, classified or shaded results stay as they are. Note a plain grey result.
- **Wrong layer type.** If you gave a layer of the wrong kind (a raster where a table is needed), the chat should refuse before running. Not a row on its own;
  note it if it happens.

## Not covered by these rows
Undo (check `undo the last operation` after any row that changed a layer), privacy gate, and layout tools: see sections 1 to 4 of the first sheet.
