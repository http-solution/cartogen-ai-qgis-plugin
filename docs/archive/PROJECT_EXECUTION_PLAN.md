# Cartogen AI Phase 1 — Delivery Control Plan

## Product objective

Deliver a working AI-first humanitarian mapping application. The user describes an objective in chat; Gemini proposes a reviewable plan; approved tools operate on real project data; the map, tables, jobs, and exports show the resulting state.

## Non-negotiable rules

- No decorative map geometry, fake pins, fake regions, fake metrics, or hard-coded source claims.
- No UI control without a real backend action or an explicit `not implemented` state.
- No user testing hand-off for unfinished work. Hermes owns automated, API, browser, and persistence verification.
- No completion claim from static checks alone.
- Provider credentials remain backend-only.
- Demo identity is development-only; browser code must not send a hard-coded organization header.
- Every AI result must show its source context, assumptions, limitations, and approval state.

## Current delivery slice

### AI-first workspace

Acceptance:

- Chat is the primary input surface.
- Map renders only stored project geometry.
- Right tools show real layers, uploads, analysis jobs, and status.
- Empty states explain how to add real data.
- Gemini system and user roles are separate.
- Browser requests do not contain a hard-coded demo tenant header.

### Real data path

Acceptance:

- GeoJSON upload persists in PostGIS and reads back.
- Document/context upload persists with provenance hash.
- AI planning uses current project context.
- Approved analysis creates a persisted job.
- Worker executes the job and persists output.
- Map and job panels read the persisted result.

## Next implementation gates

1. Replace the hard-coded project ID with a real project selector backed by a project API.
2. Add real dataset discovery/import workflow; chat may recommend sources, but imports must be explicit and read back from storage.
3. Add editable feature/property workflow with server-side validation and audit trail.
4. Add scheduled analysis jobs with persisted schedule, worker execution, and run history.
5. Add real user/organization project permissions and remove development identity from the release path.
6. Add browser-level smoke automation for the core chat → plan → approve → result journey.

## Release gates

A gate is green only when the exact user journey is executed against the live stack and read back:

```text
chat objective
→ Gemini plan
→ approve
→ persisted job
→ worker execution
→ stored result
→ map/layer/job read-back
```

Current status: AI-first workspace foundation implemented; project selection, dataset discovery/import, editing, scheduling, and production permissions remain open.
