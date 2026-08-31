# Cartogen AI Sector Product Strategy

**Status:** Active implementation strategy. Priority sectors are humanitarian aid mapping, engineering mapping, urban planning mapping, and logistics mapping.

## Market map

### Priority wave 1

1. Humanitarian aid and crisis response — strongest domain advantage and most immediate workflow evidence.
2. Engineering and infrastructure — technical GIS users with clear QA, measurement, and asset workflows.
3. Urban planning and local government — recurring land-use, accessibility, and service-catchment decisions.
4. Logistics and supply chain — route, hub, network, and coverage workflows with measurable operational value.

### Wave 2 sectors

- Agriculture and food security;
- environment, conservation, and natural resources;
- public health and epidemiology;
- disaster risk reduction and climate resilience;
- utilities, energy, and water;
- transport and mobility;
- telecoms/network planning;
- real estate and site selection;
- education and social-service access;
- tourism, heritage, and cultural resources;
- coastal, marine, and fisheries management;
- research and academia;
- public safety and lawful security analysis;
- defense and intelligence only with explicit lawful-use and governance controls.

## Product implementation model

Sector customization is layered:

1. **Profile guidance:** sector vocabulary, assumptions, safety prompts, output preferences.
2. **Quick-start workflows:** curated examples using existing tools.
3. **Sector templates:** reusable workflow presets after repeated user validation.
4. **Sector reports:** stable output schemas and branded report/export formats.
5. **Commercial integrations:** organization data, identity, governance, support, and deployment.

Do not fork the core agent per sector. Keep the execution engine, tools, safety gates, and task manager shared. Add sector guidance and validated recipes around the shared core.

## Delivery roadmap

### Phase 1 — sector guidance

- Add profile labels for all viable sectors.
- Add sector-specific prompt-refinement guidance.
- Add public documentation with example requests.
- Verify no sector profile bypasses safety or privacy rules.

### Phase 2 — humanitarian aid experience

- Humanitarian onboarding profile;
- 3W/4W presence and coverage-gap workflow preset;
- needs/severity and affected-population workflow preset;
- access/route-risk workflow preset;
- field-ready report/export template;
- synthetic-data demonstrations and design-partner validation.

### Phase 3 — engineering, urban planning, logistics

- Engineering: survey/CRS/asset QA and construction workflow templates.
- Urban planning: parcel/accessibility/service-catchment templates.
- Logistics: hub/route/network coverage templates.
- Validate each with representative users before adding commercial packaging.

### Phase 4 — sector packages

- sector-specific onboarding;
- role-based templates;
- report branding;
- training and implementation services;
- private organization data connectors;
- support and SLA options.

## Business model alignment

Community receives useful sector guidance and core workflows where they are broadly applicable and GPL-compatible. Commercial value comes from:

- managed AI access and spend controls;
- organization governance and identity;
- private/controlled deployment;
- sector onboarding and training;
- organization connectors and integrations;
- support, SLA, and operational accountability.

Do not withhold basic humanitarian, engineering, planning, or logistics capability merely to force an upgrade. Sell operational reliability, governance, integration, and service value.

## Success metrics

For each priority sector measure:

- qualified interviews;
- first successful workflow;
- time to useful output;
- weekly repeat workflow rate;
- report/export completion rate;
- support time per workflow;
- paid conversion for managed value;
- errors and unsafe/ambiguous requests;
- customer-reported decision value.

A sector moves from guidance to a commercial package only after repeated use and a documented willingness-to-pay signal.
