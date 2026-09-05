# Cartogen AI Enterprise Growth and Commercial Improvement Plan

**Owner:** HTTP-Solution / Cartogen AI
**Status:** Active business and delivery plan
**Planning horizon:** 0–18 months
**Primary sequence:** Humanitarian aid → Engineering → Urban planning → Logistics

## 1. Executive assessment

Cartogen AI has a credible product foundation: a useful Community QGIS plugin, a managed-AI commercial direction, sector-aware mapping guidance, CMS authentication, billing orchestration, and a private gateway architecture.

It is not yet enterprise-ready as a business because the operating model is incomplete. The next challenge is not adding every possible feature. It is proving a narrow, valuable workflow; packaging it for a defined buyer; delivering it safely; measuring its economics; and making procurement repeatable.

## 2. Business gaps

### G1 — Positioning is too broad

Current language covers GIS, AI, humanitarian work, engineering, planning, logistics, and enterprise deployment. A buyer must understand in one sentence:

- who Cartogen AI is for;
- which decision it improves;
- what outcome it delivers;
- why the managed service is worth paying for.

**Correction:** Lead with humanitarian operational mapping first. Use the other sectors as an expansion roadmap, not equal homepage priorities.

### G2 — No beachhead product package

The value ladder names Professional, Team, Organization, and Enterprise, but does not yet define a buyable package with seats, usage, onboarding, support, outputs, exclusions, or success criteria.

**Correction:** Create a paid Humanitarian Mapping Starter package and sell that before building a generic enterprise platform.

### G3 — Buyer and user are not separated

The GIS analyst, GIS manager, programme lead, ICT/security reviewer, procurement officer, and executive sponsor have different objections and buying criteria.

**Correction:** Create persona-specific messaging, demo flows, evidence, and sales collateral.

### G4 — No quantified proof of value

The product direction describes capabilities but not measured outcomes such as hours saved, faster coverage analysis, fewer manual errors, or improved reporting cycles.

**Correction:** Run design-partner pilots with baseline and post-adoption measurements.

### G5 — Pricing and packaging are unvalidated

Prices are intentionally hypotheses, which is correct, but there is no private pricing experiment, quote template, minimum contract value, usage model, or margin floor.

**Correction:** Test three commercial models: seat-plus-platform, organization subscription, and managed project package. Keep provider usage budgets explicit.

### G6 — Enterprise trust evidence is incomplete

The security assessment identifies remaining gates: SMTP/password reset, backups, monitoring, Python dependency audit, live Stripe, TLS/firewall, and entitlement security. There is no security questionnaire pack, DPA, subprocessors register, retention schedule, or incident-response pack.

**Correction:** Build a lightweight trust centre and evidence room before enterprise procurement.

### G7 — Customer success is not operationalized

There is no defined onboarding journey, implementation checklist, training curriculum, adoption review, support severity model, renewal process, or churn reason taxonomy.

**Correction:** Make onboarding and repeat workflow adoption explicit deliverables.

### G8 — Product telemetry and unit economics are incomplete

The strategy lists metrics but the platform does not yet provide a reliable commercial measurement layer for activation, workflow success, provider cost, support effort, retention, and gross margin.

**Correction:** Add privacy-aware event tracking and a monthly unit-economics review.

### G9 — Billing lifecycle is not production complete

The local simulated lifecycle works, but real Stripe checkout, idempotent webhook storage, retries, reconciliation, customer portal, plan-to-budget mapping, taxes/invoices, refunds, and entitlement/download controls remain incomplete.

**Correction:** Treat billing correctness as a launch gate, not a later enhancement.

### G10 — Enterprise deployment is not a product yet

Private deployment is described as a value proposition, but there is no supported reference architecture, deployment runbook, upgrade policy, backup policy, RTO/RPO, or acceptance certificate.

**Correction:** Offer one supported deployment pattern first: managed single-tenant VPS, then controlled customer deployment.

### G11 — GPL/commercial boundary needs formal review

The feature-placement principles are documented, but enterprise buyers and contributors may ask about licensing, hosted service terms, plugin/service boundaries, data ownership, and commercial extensions.

**Correction:** Obtain qualified legal review and publish plain-language boundary documentation.

### G12 — Sales pipeline and distribution are informal

Baron's humanitarian ICT/GIS experience is a strong distribution advantage, but there is no CRM funnel, qualification standard, demo script, partner motion, or proposal process.

**Correction:** Create a design-partner pipeline with stage definitions and weekly review.

## 3. Revised commercial model

### Community — adoption and trust layer

- GPL-2.0 QGIS plugin;
- useful local Ollama experience;
- documented Cartogen AI hosted connection;
- public tests, security notes, and sector workflow examples;
- no forced account for local use.

**Purpose:** adoption, credibility, contributor/community reach, and low-friction evaluation.

### Humanitarian Mapping Starter — beachhead paid offer

Target: small-to-medium humanitarian GIS teams, implementing partners, emergency consultants, and operational mapping units.

Include:

- managed Cartogen AI access;
- controlled usage budget and rate limits;
- one organization workspace;
- humanitarian mapping onboarding;
- 3W/4W and coverage-gap workflow pack;
- needs/severity and access-risk workflow pack;
- monthly usage and support review;
- documented data-handling terms;
- standard business-hours support.

Do not promise:

- unlimited usage;
- zero retention unless technically verified;
- a formal SLA until monitoring and response procedures exist;
- private deployment until the deployment package is tested.

### Team / Organization — governance offer

Target: NGOs, public-sector GIS teams, and international organizations with multiple users.

Add:

- organization administration;
- RBAC;
- SSO/SAML or OIDC;
- team-level budgets;
- audit events;
- shared workflow templates;
- project/workspace management;
- onboarding and training;
- priority support;
- annual contract and procurement pack.

### Enterprise / Controlled Deployment — assurance offer

Target: organizations requiring identity, deployment control, integration, procurement, and formal support.

Add only when implemented:

- single-tenant managed deployment or customer-controlled deployment;
- private networking and identity integration;
- retention and deletion controls;
- backup/restore evidence;
- security questionnaire and DPA pack;
- M365/SharePoint/Power BI integration;
- defined RTO/RPO;
- SLA with measured service history;
- change-management and upgrade policy;
- named technical/account ownership.

### Managed mapping services — optional revenue stream

For customers not ready to adopt a platform:

- fixed-scope situation-map production;
- coverage-gap analysis;
- route/accessibility analysis;
- map automation and reporting setup;
- implementation and training.

This creates revenue and discovery evidence without forcing every buyer into a full SaaS commitment.

## 4. Sector expansion model

### Wave 1 — humanitarian aid

Primary workflows:

- 3W/4W operational presence;
- service coverage gaps;
- affected-population and needs analysis;
- severity/vulnerability mapping;
- humanitarian access and route risk;
- situation-map and decision-report production.

### Wave 2 — engineering

- survey and CRS QA;
- asset inventory and condition;
- construction progress;
- constraints and buffers;
- quantities, measurements, and engineering reports.

### Wave 3 — urban planning

- parcels and zoning;
- land-use suitability;
- accessibility and service catchments;
- development scenarios;
- stakeholder-facing planning maps.

### Wave 4 — logistics

- hubs and depots;
- route and network analysis;
- service-level coverage;
- accessibility under hazards;
- supply-chain scenario comparison.

A sector becomes a formal package only after at least three validated workflows, two reference users, documented output templates, and evidence of repeat demand.

## 5. Enterprise task backlog

Priority levels:

- **P0:** required before accepting paid production customers;
- **P1:** required for repeatable organization sales;
- **P2:** scale, expansion, and optimization;
- **P3:** optional strategic improvements.

### Workstream A — product and positioning

- [P0] Write the one-sentence humanitarian beachhead positioning.
- [P0] Define the Humanitarian Mapping Starter package, including users, usage, outputs, onboarding, support, and exclusions.
- [P0] Create buyer/user personas and objection maps.
- [P0] Create a 30-minute humanitarian demo using synthetic or approved non-sensitive data.
- [P1] Create engineering, urban-planning, and logistics package briefs.
- [P1] Create sector-specific case-study templates.
- [P2] Add validated workflow packs and reusable presets for each priority sector.

**Acceptance:** A prospect can understand the offer, see a relevant demo, receive a consistent proposal, and know how success will be measured.

### Workstream B — design partners and evidence

- [P0] Identify 10 qualified discovery candidates.
- [P0] Conduct 10 structured interviews.
- [P0] Recruit 5 active design partners.
- [P0] Define pilot charter, data rules, success measures, and exit criteria.
- [P0] Run at least 3 paid or conversion-ready pilots.
- [P1] Produce two anonymized case studies with measured outcomes.
- [P1] Record objections, failed workflows, support time, and conversion reasons.

**Acceptance:** Three paying or formally sponsored pilot conversions and one repeat weekly workflow per participating organization.

### Workstream C — pricing and commercial packaging

- [P0] Define pricing hypotheses for Starter, Team, Organization, and Enterprise.
- [P0] Set minimum gross-margin and support-cost guardrails.
- [P0] Model seat, usage, organization, and project-based pricing.
- [P0] Define overage, suspension, refund, cancellation, and upgrade rules.
- [P1] Create quote, order form, proposal, and renewal templates.
- [P1] Define tax, invoice, procurement, and currency handling.
- [P2] Implement plan-to-budget/rate-limit mapping in the gateway.

**Acceptance:** Every quote can be costed, margin-checked, approved, billed, and supported without bespoke spreadsheet logic.

### Workstream D — billing and entitlement

- [P0] Configure Stripe test mode and verify Checkout.
- [P0] Add idempotent Stripe webhook-event storage.
- [P0] Add webhook retry, dead-letter, and reconciliation handling.
- [P0] Implement Customer Portal actions for payment method, invoices, cancellation, and plan changes.
- [P0] Implement plan-to-LiteLLM budget/rate-limit mapping.
- [P0] Build secure Pro-client artifact and entitlement/download service.
- [P1] Add refunds, failed payments, grace periods, and dunning states.
- [P1] Add admin subscription reconciliation and support override procedures.
- [P2] Add seats, invitations, and organization entitlements.

**Acceptance:** Checkout → webhook → entitlement → client activation → cancellation → grace period → reactivation is tested with no duplicate keys or orphaned access.

### Workstream E — identity and organization governance

- [P0] Finalize Directus customer role and self-read policy.
- [P0] Implement email verification and password reset through SMTP.
- [P0] Add account lockout/abuse response and authentication monitoring.
- [P1] Add organization/workspace data model.
- [P1] Add invitations and role-based access control.
- [P1] Add OIDC/SAML SSO for Organization/Enterprise.
- [P1] Add audit events for login, billing, key, export, and administrative actions.
- [P2] Add SCIM provisioning if enterprise demand supports it.

**Acceptance:** An organization administrator can safely invite, govern, audit, suspend, and remove users without exposing cross-tenant data.

### Workstream F — security, privacy, and compliance

- [P0] Install and run `pip-audit` in CI.
- [P0] Complete live TLS, firewall, reverse-proxy, and admin-access review.
- [P0] Add encrypted off-host backups and perform restore testing.
- [P0] Define retention/deletion behavior for prompts, geometry, outputs, logs, and keys.
- [P0] Publish a subprocessors and data-handling register.
- [P1] Prepare DPA, privacy notice, terms, acceptable-use policy, and incident-notification process.
- [P1] Prepare security questionnaire evidence pack.
- [P1] Add vulnerability disclosure and security incident runbooks.
- [P2] Assess ISO 27001/SOC 2 readiness only after operating controls are stable.

**Acceptance:** Procurement/security reviewers receive evidence, not promises, for every stated control.

### Workstream G — reliability and operations

- [P0] Add service monitoring for website, Directus, gateway, database, disk, and backups.
- [P0] Define support severity levels, response targets, escalation, and communications.
- [P0] Define RTO/RPO for the managed service.
- [P0] Add structured redacted logs and correlation IDs.
- [P0] Add provider failure, quota, and degraded-mode procedures.
- [P1] Test restart, restore, rollback, and key-revocation procedures.
- [P1] Define change windows and customer communication policy.
- [P2] Add multi-region or secondary-provider resilience if justified by contracts.

**Acceptance:** HTTP-Solution can detect, communicate, recover, and learn from a production incident.

### Workstream H — customer success and delivery

- [P0] Create onboarding checklist and customer technical questionnaire.
- [P0] Create humanitarian GIS training curriculum.
- [P0] Define first-value milestone within the first onboarding session.
- [P0] Create support portal/email process and knowledge base.
- [P1] Add 30/60/90-day adoption review.
- [P1] Define renewal and expansion playbook.
- [P1] Track churn and failed activation reasons.
- [P2] Create partner/consultant implementation programme.

**Acceptance:** A new customer can move from signed order to first useful map through a repeatable process owned by someone other than the founder alone.

### Workstream I — sales and partnerships

- [P0] Define CRM stages: target, qualified, discovery, pilot, proposal, procurement, won/lost.
- [P0] Create qualification criteria and disqualification rules.
- [P0] Build humanitarian-sector account list and outreach sequence.
- [P0] Create proposal, demo, security, and pilot collateral.
- [P1] Develop NGO, humanitarian consultant, QGIS, and implementation partners.
- [P1] Create referral and reseller rules.
- [P2] Develop public-sector framework/procurement strategy.

**Acceptance:** Pipeline is visible, forecastable, and reviewed weekly with next actions and evidence.

### Workstream J — measurement and management

- [P0] Define product funnel: install → connect → first workflow → repeat workflow → paid conversion.
- [P0] Define event taxonomy with privacy limits.
- [P0] Measure provider cost per successful workflow.
- [P0] Measure onboarding hours, support hours, activation failures, and gross margin.
- [P1] Build internal commercial dashboard.
- [P1] Review retention, expansion, churn, and contribution margin monthly.
- [P2] Add sector-level profitability and capacity planning.

**Acceptance:** Product and commercial decisions are based on measured usage and margin, not intuition alone.

## 6. 90-day execution sequence

### Days 1–30 — prove the beachhead

1. Finalize humanitarian positioning and Starter package.
2. Prepare demo, pilot charter, pricing hypotheses, and discovery script.
3. Contact and interview 10 qualified organizations.
4. Configure Stripe test mode and complete billing lifecycle.
5. Complete Pro-client entitlement/download design.
6. Install Python dependency audit in CI.
7. Complete VPS TLS/firewall/backup baseline.

### Days 31–60 — run controlled pilots

1. Recruit five design partners.
2. Run at least three structured pilots.
3. Measure first value, repeat workflows, cost, support, and failure reasons.
4. Implement organization/workspace model and basic RBAC.
5. Produce first case study and security evidence pack.
6. Create onboarding and support operating procedures.

### Days 61–90 — make delivery repeatable

1. Convert at least three pilots to paid or formally sponsored contracts.
2. Publish validated Starter pricing privately.
3. Complete customer portal, invoices, cancellation, and reconciliation.
4. Establish monthly customer-success and unit-economics reviews.
5. Prepare engineering, urban-planning, and logistics expansion briefs.
6. Decide which humanitarian workflows become stable commercial templates.

## 7. Enterprise readiness definition

Cartogen AI should be called enterprise-ready only when all of the following are true:

- one priority sector has a repeatable paid package;
- at least three paying organizations use it repeatedly;
- onboarding and support do not depend entirely on the founder;
- billing and entitlements are idempotent and reconciled;
- organization identity and RBAC are tested;
- security/privacy documents match implemented controls;
- backups, restore, monitoring, and incident response are exercised;
- gross margin and provider cost are measured;
- procurement and renewal materials are ready;
- Community/commercial boundaries remain clear;
- the service can honestly state what it does not yet provide.

## 8. Recommended management cadence

- Weekly: pipeline, delivery blockers, pilot health, security incidents, cash commitments.
- Fortnightly: product release review and customer feedback synthesis.
- Monthly: unit economics, retention, support load, infrastructure cost, roadmap priority.
- Quarterly: sector expansion decision, pricing review, risk register, enterprise readiness gate.
