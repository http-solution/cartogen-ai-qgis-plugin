# Cartogen AI Workspace — Private Legal and Trust Review Checklist

This checklist is for qualified legal and security review. It is not legal advice.

## Product naming and branding

- [ ] Confirm Cartogen AI Workspace name does not imply QGIS endorsement.
- [ ] Confirm use of “inspired by QGIS workflows” is accurate and non-misleading.
- [ ] Avoid QGIS marks, logos, screenshots, or copied interface text in marketing.
- [ ] Review Cartogen trademark and product naming strategy.

## Source and dependency provenance

- [ ] Create a dependency inventory with licence, version, source, and notice obligations.
- [ ] Review MapLibre, OpenLayers, PostGIS, tile, queue, storage, and auth dependencies.
- [ ] Maintain a clean-room implementation record.
- [ ] Review any QGIS Server or QGIS-linked component before integration.
- [ ] Confirm source-available obligations for any GPL component used in distribution.
- [ ] Keep attribution and licence notices in the product and release artifacts.

## Commercial terms

- [ ] Define hosted-service terms.
- [ ] Define data ownership and customer content rights.
- [ ] Define output ownership and reuse.
- [ ] Define retention and deletion.
- [ ] Define service suspension and quota terms.
- [ ] Define refund and cancellation terms.
- [ ] Define support and SLA commitments only after operational evidence.
- [ ] Define acceptable-use and prohibited-use terms.

## Data protection

- [ ] Review humanitarian-sensitive data handling.
- [ ] Define personal-data minimization and aggregation defaults.
- [ ] Define data residency options.
- [ ] Define subprocessors and provider responsibilities.
- [ ] Prepare privacy notice and DPA.
- [ ] Define breach/incident notification process.
- [ ] Define export and deletion response process.

## AI governance

- [ ] Document models/providers and routing.
- [ ] Document prompt/output retention.
- [ ] Document human review requirements.
- [ ] Document limitations and hallucination/error handling.
- [ ] Define customer data exclusion from training unless explicitly agreed.
- [ ] Define restricted or sensitive use cases.

## Enterprise security

- [ ] Threat model tenancy, uploads, jobs, exports, and collaboration.
- [ ] Review authorization at every API boundary.
- [ ] Review signed download links and expiry.
- [ ] Review upload malware scanning and file limits.
- [ ] Review audit events and log redaction.
- [ ] Review backups, restore, RTO, and RPO.
- [ ] Prepare security questionnaire evidence.
- [ ] Define vulnerability disclosure and incident response.

## Approval gate

No production implementation or external commercial claim should rely on this checklist being “complete” until qualified counsel and security review have recorded decisions for the applicable deployment model.
