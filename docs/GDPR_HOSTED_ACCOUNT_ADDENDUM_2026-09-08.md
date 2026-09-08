# GDPR technical addendum -- Hosted-Account feature (`agent/account.py` / `ui/account_dialog.py`)

**Status: DRAFT technical analysis, not a compliance determination.** This document does what
an engineer can responsibly do -- inventory exactly what personal data the Hosted-Account
feature touches, where it goes, and how it's stored, verified directly against the live code
(not assumed) -- and stops there. Whether that inventory is *compliant* is a legal judgment
this document does not make. Per Cartogen's operating rules, this is not legal advice; Baron
(or whoever he designates for this) should review it and fold the parts that hold up into
`docs/GDPR_COMPLIANCE_REVIEW.docx` proper, alongside refreshing that document's stale
`cartogen-ai-community`/`01d853f` framing (see `docs/CODE_REVIEW_2026-09-08.md` section 5).

This addendum exists to close the informational half of `BUG-2026-09-08-2`: **correction, 2026-09-08** -- this paragraph originally said the review predated the feature; verified against `git log` and that's wrong. `agent/account.py` was added 2026-08-28 (`e045cb2`), before the review's own 2026-09-01 date -- the feature already existed when the review was written. What actually happened is a scope gap, not a timing gap: the review's own file list and Section 3.2/3.3 discussion cover only the inert `providers/cartogen.py` LLM-provider stub (a different "hosted" surface -- the Settings dropdown's provider option, not this account/login feature), and never mention `account.py`/`account_dialog.py` at all. The *decision* half of that bug (extend the official review, or defer/disable the feature) is still Baron's call -- see "Open decision" at the end.

## 1. What the feature is

Added 2026-08-28. Lets a user create or sign in to a Cartogen-hosted account from inside the
QGIS plugin (`ui/account_dialog.py`), so the plugin can call a hosted Cartogen API under that
account's identity instead of (or alongside) a self-supplied provider key. `agent/account.py`'s
`CartogenAccountClient` is a thin HTTP client against a configurable `base_url` (Settings ->
Cartogen AI account URL; defaults to `http://localhost:3000`, i.e. this talks to whatever
service Baron's own deployment points it at -- it is not, itself, a fixed third-party endpoint
baked into the plugin).

## 2. Personal data inventory

Verified directly against `agent/account.py`'s request bodies and `ui/account_dialog.py`'s
fields -- not inferred from the feature name.

| Data element | Collected when | Sent to | Stored locally? |
|---|---|---|---|
| Email address | Register, login | `base_url`/`auth/register`, `/auth/login` | No -- only held in the QLineEdit widget for the session; not written to `QSettings` or disk. |
| Password | Register, login | Same, in the JSON body, over HTTPS as of today's fix (`BUG-2026-09-08-1`) | Never. `account.py`'s own module docstring states passwords "never enter logs, settings text, or return messages," and this holds on inspection -- `register`/`login` return dicts never include the raw password, and neither method logs it. |
| First / last name | Register only (optional fields) | `/auth/register` | No -- same as email; also briefly re-displayed (fetched fresh via `current_user()`) in the dialog's status label when reopened, not cached to disk. |
| Session cookie / bearer token | Returned by the server on successful login | N/A (received, not sent onward) | **Yes.** Persisted via `CredentialManager.get_account_session()`/`_save_auth_secret()` (`agent/auth.py`), which stores it through `QgsAuthManager` -- the same encrypted-credential path already documented in `SECURITY.md` for provider API keys. Unlike the general API-key path, `_save_auth_secret` here has **no plaintext fallback**: if the auth manager is disabled or unavailable, the save simply fails (returns `False`) and the session is not persisted at all, rather than being written in the clear. This is a stricter posture than provider keys get, not a weaker one. |
| Cartogen account base URL | Settings dialog | N/A (local only) | Yes, in plain `QSettings` (`cartogen_ai/account_base_url`) -- this is a server address the user configured, not personal data about them. |

No other personal data (no device identifiers, no telemetry, no analytics) is collected by
this feature. It does not touch `memory.py`'s project/global notes system, so it is unrelated
to findings F6/F7 (always-on project memory, no export path) -- those stay exactly as already
described in the main review.

## 3. Where the data actually goes

The controller/processor question that usually dominates a GDPR analysis is unusually simple
here **if** `base_url` points at infrastructure Baron's own organization operates: in that
case this is Baron's own service receiving Baron's own users' account data, the same
relationship as any first-party login system, not a transfer to a third-party processor. If
`base_url` is ever pointed at a Cartogen-operated hosted service run by someone other than
Baron's org, that changes the analysis (processor/sub-processor obligations, a real DPA would
be needed) -- this document can't determine which of those is true from the code alone; that's
a fact about deployment, not about this plugin, and is worth confirming explicitly rather than
assumed either way.

## 4. Transport and storage security, as of today

- **Transport:** as of this session's fix for `BUG-2026-09-08-1`, plain `http://` is rejected
  for any non-loopback host, so a real deployment's email/password traffic can no longer
  silently go out in the clear while the UI claims HTTPS -- closing the gap this addendum was
  originally going to have to flag on its own.
- **At rest:** the only thing persisted locally is the session token, through the same
  encrypted-by-default path as provider API keys, with (per section 2) no plaintext-fallback
  branch for this specific secret. `logout()` clears the in-memory cookie jar and
  `CredentialManager.clear_account_session()` removes the stored one.

## 5. Gaps against a GDPR framework (informational -- not a compliance ruling)

- **No in-app privacy notice before registration.** This is the same underlying gap as the
  main review's F2 (no in-app privacy notice, still open), but this feature makes it more
  concrete: F2 was written when the only personal-context surface was optional memory notes;
  registering a real hosted account with email/name/password is a much more typical
  "notice and consent" trigger. Recommend F2's remediation explicitly cover this dialog when
  it's addressed.
- **No in-plugin account-deletion / data-export affordance.** `CartogenAccountClient` has no
  `delete_account`/`export_my_data` method, and `account_dialog.py` has no corresponding UI.
  A user can sign out (removing the local session token) but any erasure or portability
  request for their registered email/name/password would have to be handled server-side, by
  whatever operates `base_url` -- the plugin itself provides no self-service path. Whether
  that's acceptable depends on what the server side already offers, which this document has
  no visibility into.
- **No documented retention policy** for how long the hosted service keeps a registered
  account's data after the user stops using the plugin -- again a server-side fact, not
  something in this codebase.

## 6. Open decision (Baron's, not this document's)

`docs/GDPR_COMPLIANCE_REVIEW.docx` needs one of:

1. **Extend it** to formally cover this feature -- fold in sections 2/4/5 above, refresh the
   stale `cartogen-ai-community`/2026-09-01/`01d853f` framing at the same time (already
   flagged in `docs/CODE_REVIEW_2026-09-08.md` section 5), and have it actually reviewed by
   whoever Baron treats as this project's compliance reviewer (this document is an
   engineering input to that, not a substitute for it); or
2. **Defer or disable** the feature until that review happens.

Nothing in this addendum argues for one over the other -- it only tries to make sure whichever
choice gets made, it's made with an accurate, verified picture of what the feature actually
does, rather than the guess a stale document would otherwise invite.
