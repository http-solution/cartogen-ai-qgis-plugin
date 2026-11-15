# Project status dashboard: how it is built and refreshed

A private Claude Artifact (a "Dashboard" page) shows the project's status: version and counts, how much has been checked by hand, the latest hand-test run, defects, open work and recent changes. Its link is given in the scheduled task's prompt and is not kept in this public repository. Nothing on the dashboard is a live query: it shows five data files, and a refresh replaces those files.

## What feeds it

| Dataset id | File | Comes from |
|---|---|---|
| `summary` | `summary.json` | `tools/dashboard_snapshot.py`: version (`metadata.txt`), tool count (registry), ledger, plans, master task list, test counts, open pull requests |
| `work_items` | `work_items.json` | the open rows of `docs/MASTER_TASK_LIST_*.csv` |
| `activity` | `activity.json` | the last 25 commits on `origin/main` |
| `hand_tests` | `hand_tests.json` | `docs/dashboard_data/hand_tests.json`, **kept by hand** |
| `defects` | `defects.json` | `docs/dashboard_data/defects.json`, **kept by hand** |

Update the two hand-kept files in the same pull request that changes a hand-test result or a defect's state; the dashboard will then show it at the next refresh. They are small lists of row objects (the columns are pinned by `tests/test_dashboard_snapshot.py`).

## How "verified by hand" is counted

Only a ledger entry whose `hand_verified` text starts with "hand-tested", or says the owner looked, counts as **Verified by hand**; "partly..." counts as partly verified; everything else, including text the rule does not recognise, counts as **not** hand-verified. The first version counted everything that did not start with "not" and overstated the figure (7 instead of 3), so the rule leans the other way on purpose. Offline tests and CI never count.

## Refresh (what the scheduled task does, and what to do by hand)

1. `git checkout main && git pull`.
2. Find the number of open pull requests (GitHub) and write one short note for the dashboard (for example "PR 556 waiting on CI", or empty).
3. `python tools/dashboard_snapshot.py --out <a new empty folder> --run-tests --open-prs N --open-pr-note "..."` (the test run takes about two minutes; a number of errors from this environment that also occur on a clean checkout are reported as `tests_sandbox_errors`, not hidden).
4. For each of the five files, upload it to the dashboard artifact as an asset (the Artifact tool, `asset: true`, `url` = the dashboard, `file_path` = the file). Each upload returns a `/_blob/<id>` url.
5. For each dataset id above: read `datasets/<id>`, then `update` it with `source.url` = the new blob url, `updated: {at: <UTC now>, by: "claude"}` and `edit: {via: "claude", at: <UTC now>}`, pinned with `if_version`. Then delete the previous asset (the id in the old url) so uploads do not pile up.
6. Do not change the page (`files/index.html`) in a refresh.
7. If a step cannot be done (no GitHub access for the pull-request count, a failed upload), leave that dataset as it was, and say which in the run's last line; never write a guessed number.

## Limits

- The numbers are as of the refresh time shown on the page, not live.
- `open_prs` and the test counts are not readable from a checkout; a refresh without GitHub access or without `--run-tests` shows 0 for them, which the note should say.
- The hand-test and defect tables are only as current as the last pull request that edited `docs/dashboard_data/`.
