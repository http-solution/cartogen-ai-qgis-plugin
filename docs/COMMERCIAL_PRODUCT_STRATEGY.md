# Cartogen AI Commercial Product Strategy

**Status:** Working strategy for HTTP-Solution decision-making. Pricing and packaging remain hypotheses until validated with paying design partners.

## Product architecture

Cartogen AI has two coordinated products:

### Community

- GPL-2.0 QGIS plugin;
- useful on its own;
- Ollama local LLM or Cartogen AI hosted connection;
- transparent tools, tests, documentation, and security controls;
- no account requirement for local use.

### Commercial

- managed Cartogen AI service access;
- organization-level administration and usage governance;
- onboarding and priority support;
- controlled/private deployment options when justified;
- integrations with enterprise humanitarian workflows;
- service commitments that HTTP-Solution can actually operate.

The commercial product should add operational reliability and organizational value, not cripple Community to create artificial upgrade pressure.

## Initial ideal customer profile

Prioritize customers with a recurring spatial workflow, a real need for support or governance, and a budget for operational software:

1. humanitarian GIS teams;
2. NGOs and implementing partners with field-mapping workflows;
3. emergency-response consultants;
4. public-sector and international organizations with QGIS-heavy operations;
5. specialist GIS teams that need controlled AI access without managing provider keys individually.

Baron's humanitarian ICT and GIS experience is the initial distribution advantage. Product claims must remain grounded in workflows that can be demonstrated with representative, non-sensitive data.

## Value ladder

### Community — free/open source

Value: core QGIS spatial-AI capability, local operation, transparent execution, and a low-friction way to evaluate Cartogen AI.

### Professional — managed access

Value: hosted Cartogen AI access, managed model routing, usage controls, key lifecycle, onboarding, priority fixes, and a predictable support path.

### Team/Organization — operational governance

Value: shared administration, team usage policies, audit visibility, workflow templates, higher support level, and integration assistance.

### Enterprise — controlled deployment and integration

Value: identity integration, RBAC, private/controlled deployment, retention controls, security review, Microsoft 365/SharePoint/Power BI integration, SLA, and procurement support.

Enterprise features must not be promised until they have a tested implementation, an operating procedure, and a security/legal review.

## Pricing approach

Do not hard-code pricing into the public repository. Test pricing privately with design partners.

Initial hypothesis to validate:

- Professional: individual managed access at a low monthly price;
- Team: several seats, shared governance, onboarding, and support;
- Organization: annual contract with workflow integration and support;
- Enterprise: annual contract based on deployment, identity, integration, and SLA scope.

The first commercial milestone is not a theoretical revenue target. It is evidence of willingness to pay:

- 10 qualified discovery conversations;
- 5 active design partners;
- 3 paying conversions;
- one repeat weekly workflow per paying organization;
- gateway cost and support effort measured for each active customer.

## Unit-economics guardrails

Before scaling managed access, measure:

- model/provider cost per successful workflow;
- average and 95th-percentile usage per customer;
- support time per account;
- onboarding time;
- infrastructure and observability cost;
- gross margin after provider and support costs;
- churn and failed-activation reasons.

Every managed plan needs explicit budgets, rate limits, abuse controls, and a documented customer communication path when limits are reached.

## Feature-placement decision test

A feature is a Community candidate when it:

- improves the core desktop GIS workflow;
- has broad user value;
- is compatible with GPL-2.0 distribution;
- can work locally or through the documented Cartogen connection;
- does not require HTTP-Solution to operate a customer-specific service;
- can be tested and supported publicly.

A feature is commercial/private when its primary value comes from:

- managed infrastructure or provider-cost control;
- organization identity, RBAC, audit, or retention policy;
- private deployment or customer-specific configuration;
- paid onboarding, integration, SLA, or support;
- proprietary operational automation that should not be distributed with the Community plugin.

When uncertain, prefer the smallest useful Community implementation and document the commercial extension privately.

## Go-to-market sequence

1. Keep Community stable and professionally documented.
2. Complete the hosted Cartogen gateway as a controlled private service.
3. Run a paid design-partner beta with synthetic or approved non-sensitive workflows.
4. Measure activation, repeat usage, cost, support, and conversion.
5. Productize the most repeated humanitarian workflows.
6. Add organization governance and integrations only after demand is demonstrated.
7. Create annual commercial contracts once deployment and support are repeatable.

## Legal and trust gates

Before shipping private commercial modules or enforcing paid access:

- confirm GPL/open-core boundaries with qualified legal counsel;
- document data handling and retention;
- define whether geometry, prompts, outputs, and logs are retained;
- review humanitarian-sensitive data risks;
- document provider/subprocessor responsibilities;
- avoid implying certifications, zero retention, SLA, SSO, or private deployment before they exist and are tested.

## Success criteria

The commercial strategy is working when HTTP-Solution can demonstrate:

- a stable Community install path;
- a reliable managed Cartogen workflow;
- positive repeat usage by paying organizations;
- measured and acceptable gross margin;
- a repeatable onboarding/support process;
- a feature boundary that users understand and do not experience as arbitrary lock-in.
