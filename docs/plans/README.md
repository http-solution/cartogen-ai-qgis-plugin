# Plans

A feature, a fix that changes behaviour, or a test campaign starts as a plan in this folder, in the same pull request as the first line of code, and the plan is
updated in the same pull request as every later step. Why: three times in this project a finished job was quietly broken by a later change (the rc23 router
regression, the rc40 routing gap, the rc46 fragment guard) because nothing said what "finished" meant or what protected it.

A plan is short. It has exactly these headings (`tests/test_plans.py` checks them) and a `Status:` line that is one of `planned`, `in progress`, `done`, `abandoned`:

| Heading | What goes under it |
|---|---|
| `## Goal` | One paragraph: what a user can do afterwards that they cannot do now, and the issue numbers. |
| `## Scope` | What is in, and what is explicitly out (so the plan cannot grow silently). |
| `## Acceptance` | Observable checks that decide "done": the exact request a user types and what must happen. Say which are offline, which are CI-live and which need a hand test. |
| `## Guard tests` | The tests that will keep it working, as `tests/file.py::Class::test` (the same references as `docs/FEATURE_LEDGER.json`), or "none, because ..." with the reason. |
| `## Rollback` | How to undo it if it goes wrong in the field (a setting, a revert, a release to skip). |
| `## Status log` | Dated lines, newest last: what was done, the pull request, what was verified and how. Never rewrite an old line; add a new one. |

Rules that go with it (CONTRIBUTING.md section 10):
1. No behaviour change without a plan line and a ledger entry (`docs/FEATURE_LEDGER.json`) naming its guard tests.
2. `python tools/ledger_guard.py` before you push: it runs the guards of every ledger feature your change touches.
3. A plan is `done` only when its acceptance is met AND its status log says what was hand-verified. CI-only is written as CI-only.
4. Plans are living records, not frozen history: correct them as facts change, and say so in the status log.
