# Cartogen AI Release Governance

This private document defines how HTTP-Solution versions, releases, public/private changes, and feature-placement decisions are managed.

## Version rule

Every significant change receives a version and a release record.

Use Semantic Versioning:

- **MAJOR:** incompatible plugin architecture, settings migration, licensing boundary, or public API change.
- **MINOR:** backward-compatible feature or provider-surface addition.
- **PATCH:** backward-compatible bug fix, documentation correction, packaging repair, or security fix.

The version must be synchronized in:

- `metadata.txt`;
- `pyproject.toml`;
- `CHANGELOG.md`;
- the Git tag;
- the GitHub release title and release notes;
- the attached release ZIP name.

## Release channels

### Community/public

Repository: `cartogenai-glitch/cartogen_ai_community`

A public release must contain only the Community scope. It must include test evidence,
security notes, installation instructions, and a clear statement when live QGIS verification
is incomplete.

### Commercial/private

Repository: `cartogenai-glitch/CARTOGEN-AI`

The private release may contain managed gateway, organization, deployment, support,
enterprise integration, and commercial operations code. It must not be treated as public
or used as the source for a Community ZIP.

## Required gates for every significant change

1. Identify the affected channel: Community, Commercial, or both.
2. Add or update tests before implementation where behavior changes.
3. Run the relevant automated suite.
4. Run Python compilation and packaging checks.
5. Update security notes for trust-boundary or credential changes.
6. Update the correct changelog.
7. Build and audit the release artifact.
8. Create the appropriate tag and GitHub release.
9. Record the decision and evidence in `docs/OPERATIONS_LOG.md`.

## Public/private synchronization

The public repository is not a blind copy of the private repository.

For a change considered for both channels:

1. Implement and test the reusable Community-safe core first.
2. Decide whether the commercial layer adds managed operations or customer-specific value.
3. Publish only the Community-safe portion publicly.
4. Record the feature-placement decision in the private log.
5. Use separate release notes where the commercial build has additional capabilities.

Never copy private service code, billing code, customer data, credentials, pricing internals,
private deployment configuration, or organization-specific integration code into the public tree.

## Business-model guardrails

The commercial product must sell operational value rather than artificial removal of core GIS capability.

Commercial differentiation should come from:

- managed and reliable hosted access;
- team administration and shared governance;
- organization identity, audit, and support;
- private or controlled deployment;
- Microsoft 365 and operational-system integrations;
- humanitarian workflow onboarding and templates;
- service-level commitments and professional support.

Community remains a useful, independently valuable GPL-2.0 product.

## Documentation rule

Every feature-placement decision must be visible in at least one of:

- public Community scope/release documentation;
- private commercial strategy;
- private operations log;
- the relevant changelog and GitHub release notes.

No significant release should exist only as an undocumented commit.
