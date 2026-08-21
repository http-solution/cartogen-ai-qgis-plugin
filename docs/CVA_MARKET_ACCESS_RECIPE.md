# CVA Market-Access Recipe — What GIS Can and Can't Answer

**Status: Recipe, not a spec.** Composes tools that already exist and ship today
(`population_access_gap`, and optionally `run_query`) -- no new code. The value here is the
research grounding and the honest scope boundary, not a new tool.

## Research grounding (sourced, not assumed)

Cash and Voucher Assistance (CVA) feasibility is a CALP Network-defined pre-condition checklist with
**four** areas, only one of which is GIS-computable:

1. **Market conditions** (functioning, accessible markets) -- **partially GIS-computable**: physical
   accessibility/distance is a spatial question; market *functionality* (are goods actually
   available, are prices stable) is not something this plugin can observe from geometry alone.
2. **Safe and reliable operational conditions** -- not GIS-computable from this plugin's data;
   overlaps with `docs/ROUTE_RISK_AND_NOGO_ZONES_SPEC.md`'s incident/no-go-zone tools for the
   *routing safety* angle, but "operational conditions" as CALP means it (access negotiation,
   security clearance) is broader than that.
3. **Recipient needs and preferences** -- a survey/consultation question, not a spatial one.
4. **Community and political acceptance of cash** -- a survey/consultation question, not a spatial
   one.

**No universal distance threshold exists** for what counts as "market access" -- checked directly
rather than assumed: published research shows median household-to-market distances ranging from
~4km (lowland Cambodia) to ~9km (highland Cambodia) to studies focused on a 0-2km band in Kenya.
Humanitarian guidance treats "sufficiently accessible" as context-specific, set by a local market
assessment, not a fixed number this plugin should hardcode. Some cited operational thresholds for
CVA appropriateness more broadly (e.g. markets covering at least 50% of essential-goods needs,
financial service providers able to disburse to 90%+ of beneficiaries within 72 hours) come from
cluster-level cash guidance, not a single global standard -- treat as illustrative of the kind of
criteria used, not as fixed values to build a tool around.

## What's actually free today: population beyond reasonable market/FSP distance

`population_access_gap` (`agent/tools/logistics_tools.py`) already computes exactly the
GIS-computable piece of pre-condition 1 -- "how many people, and what percentage, are beyond a
given travel distance/time from the nearest facility" -- when the facility is a market or financial
service provider (FSP) agent location instead of a health clinic or warehouse:

```
population_access_gap(
    facility_layer="markets",              # or "fsp_agent_locations"
    road_network_layer="roads",
    population_raster_layer="worldpop_pop",
    area_layer="target_area",
    travel_cost=<a locally-determined distance/time, not a hardcoded default>,
)
```

**If a real market assessment already flagged which markets are actually functional** (a field like
`functional` or `status` from a REACH/CALP-style survey the user has, not something this plugin
infers), filter to only those markets first -- also zero new code:

```
run_query(layer_name="markets", expression="functional = 1")
population_access_gap(facility_layer="markets", ...)   # same layer name, now filtered in place
```

`run_query` applies a `setSubsetString` filter on the layer in place (`agent/tools/vector_tools.py`),
so the *same* layer name subsequently only exposes the functioning subset to `population_access_gap`
-- no extract-to-new-layer step needed. (Previously documented here as `filter_features`, a literal
one-line pass-through to `run_query` with no functional difference -- removed as a duplicate
registration; see CHANGELOG.md.)

## What this recipe explicitly does NOT answer

Stated plainly so it's never presented as a full feasibility verdict: this recipe answers "how many
people lack reasonable physical access to a market/FSP location" -- one input to pre-condition 1,
not a CVA feasibility determination. It says nothing about price stability, supply-chain
functionality, FSP disbursement capacity, security/access conditions, recipient preferences, or
community acceptance (pre-conditions 1's other half, and pre-conditions 2-4 entirely). A full
feasibility call needs a real market assessment and community consultation -- data this plugin has
no way to source and should never fabricate, consistent with the anti-fabrication stance already
established throughout `agent/prompts.py`.

## Prompt guidance (shipped alongside this doc)

`agent/prompts.py` rule 37 teaches the model to recognize "is cash/voucher assistance feasible
here" / "how far are people from markets" intent and map the *market-distance* piece to this
composition -- while stating plainly, every time, that market-access distance is one input to CVA
feasibility, not the whole answer, and naming what else a real feasibility call needs (market
functionality, FSP capacity, security conditions, community acceptance) so the response never reads
as a complete feasibility verdict.
