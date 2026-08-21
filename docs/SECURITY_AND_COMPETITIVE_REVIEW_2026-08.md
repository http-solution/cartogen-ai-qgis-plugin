# Security & Competitive Review — 2026-08-17

**Role framing:** software engineer / cybersecurity consultant / field GIS analyst pass over the
current codebase and market position. Two different confidence levels apply in this document, stated
plainly rather than blended together:

- **Part A (security)** is checked against real code, file:line, the same standard as `SECURITY.md`
  itself — every claim here can be verified directly.
- **Part B (competitive landscape)** is sourced from public marketing pages, plugin-repository
  listings, and vendor blog posts (see Sources at the end) — I have not read any competitor's source
  code. Treat feature claims about other products as "what they publicly claim," not independently
  verified fact, the same skepticism this project has applied to its own claims all along.

---

## Part A — Security: new attack surface since the last audit

`SECURITY.md` was last substantively updated for the protections in place through the v1.0.1/v1.2.0
hardening passes. Two real features have shipped since then that touch the threat model and aren't
mentioned there at all: the recurring monitoring scheduler (`agent/scheduler.py`,
`agent/tools/monitoring_tools.py`, v1.2.2) and the prompt refinement layer (`agent/prompt_refiner.py`,
v1.2.1/1.2.5). Reviewed both against the same adversarial standard `SECURITY.md` § "Testing performed"
already sets.

### A.1 Recurring monitoring scheduler — three real gaps, one documentation gap

The tool-allowlist control here is genuinely solid and correctly enforced: `_load_steps()`
(`monitoring_tools.py` line 65) rejects any preset step naming a tool outside
`_ALLOWED_WORKFLOW_TOOLS` (7 read-only analysis tools) before it's ever scheduled — verified this is a
real check, not just a docstring claim. That said:

1. **No minimum interval floor.** `WorkflowScheduler.start()` (`scheduler.py` line 48) only rejects
   `interval_minutes <= 0` — nothing stops `interval_minutes=0.001`, which becomes a ~60ms `QTimer`
   (`int(0.001 * 60 * 1000)`). Each tick re-runs full geoprocessing (zonal statistics, severity
   scoring) on the main Qt thread. A single miscalibrated or prompt-injected
   `schedule_recurring_workflow` call becomes a self-inflicted denial-of-service against the user's own
   QGIS session — the GUI thread the whole plugin depends on. **Recommend:** a floor, e.g. reject
   anything under 1 minute, matching how the plugin already treats other numeric tool inputs
   defensively elsewhere (e.g. `interval_minutes <= 0` today).
2. **No cap on concurrently active schedules.** Nothing stops a model from calling
   `schedule_recurring_workflow` for many different `preset_name`s — each spins up its own independent
   `QTimer` (`self._timers` has no size check). No aggregate resource limit exists. **Recommend:** a
   small constant cap (e.g. 5 concurrent schedules), enforced in `WorkflowScheduler.start()`, with a
   clear error telling the model/user to stop one first.
3. **`presence_file_path` becomes a silently-repeating local file read.** `calculate_presence_gap`
   takes a raw local file path (`analysis_tools.py` line 450, confirmed opened directly via Python
   `open()` in `reporting_tools._read_tabular_rows`, no URL/SSRF surface — that part's fine). A
   monitoring preset that includes this tool bakes that path into the schedule: `run_monitoring_workflow`
   re-reads it, unattended, on every tick, for as long as the schedule runs. `SECURITY.md`'s existing
   "Local file access is intentionally broad" limitation already accepts this risk for a one-shot,
   explicit tool call — this is a real escalation of that same accepted risk into something automatic
   and recurring, not a new vulnerability class, but worth stating explicitly rather than leaving it
   implicit.
4. **None of the above is documented in `SECURITY.md`.** The document explicitly positions itself as
   "checked against the code, not trusted on its own" — right now, an auditor reading it in good faith
   would have no way to know this entire execution path exists. This is the most important finding of
   the four: it's a completeness gap in the one document whose whole job is completeness.

**Recommended fix package:** add a `## 8. Recurring monitoring scheduler` section to `SECURITY.md`
covering the allowlist control (real, working) and findings 1–3 above (either fixed, or explicitly
accepted with the same honesty the rest of the document already uses for its other accepted risks).

### A.2 Prompt Refinement Layer — one-line addition, not a new risk class

`agent/prompt_refiner.py`'s `refine()` sends the user's raw message to the same already-configured
provider a second time (once for refinement, once for the real turn) when the feature is enabled.
Same credentials, same trust boundary as the rest of the plugin — not a new vulnerability — but it
does mean enabling this feature doubles how many times a given message leaves the machine to an
external provider. Worth a one-line mention in `SECURITY.md`'s protections list for completeness,
and it's a small piece of supporting evidence for `PRODUCT_TIERS.md`'s existing honest statement that
Enterprise's "private data enclaves, zero-retention" claim isn't real yet — every optional feature
that adds an extra external call is one more thing that claim would eventually need to account for.

### A.3 Plugin identity: a live naming collision worth resolving before public submission

This isn't a code vulnerability, but it's exactly the kind of thing a field security/compliance
reviewer should flag before a public listing goes live, and it's concrete, not speculative:

- This project's `metadata.txt` still points `repository`/`tracker`/`homepage` at
  `github.com/baron-dev07/qgis_ai_assistant` — the project's pre-rebrand name.
- A **live, already-published** listing exists on the official QGIS Plugin Repository at
  `plugins.qgis.org/plugins/qgis_ai_assistant/`, titled "QGIS AI Assistant" — the exact same slug.
  I have not inspected that listing's actual code or ownership, so I can't say whether it's related to
  this project's own pre-rebrand history or a genuinely unrelated third party — but either way, the
  slug is taken.
- This is very likely *why* the parallel `Cartogen AI/cartogen_ai/` identity and `build_cartogen_ai.py`
  exist at all (README already documents this tree as "used to ship a second QGIS plugin listing")
  — this finding is consistent with, and gives a concrete external reason for, a decision that was
  already made. `metadata.txt`'s `name=Cartogen AI` field is already correct for submission purposes.
- **What's still inconsistent:** the `repository`/`tracker`/`homepage` URLs (both trees, per the
  `build_cartogen_ai.py` propagation) still say `qgis_ai_assistant`, not a Cartogen-AI-named repo.
  **Recommend:** before any QGIS Plugin Repository submission (already flagged as a blocking item in
  `QGIS_AI_Agent_PRD.md` §7 pending a help panel), rename/create the canonical public repo to something
  Cartogen-AI-specific and update these three metadata fields — both to avoid brand confusion with
  the existing `qgis_ai_assistant` listing and because a plugin's public repo URL becomes a permanent,
  hard-to-change identity once real users depend on it.

---

## Part B — Competitive landscape (2026-08-17, sourced)

`QGIS_AI_Agent_PRD.md` §5 already has a detailed internal analysis of one competitor, Atlas (atlas.co)
— not re-derived here. This section adds what wasn't covered: the enterprise incumbent, the actual
population of other AI-driven QGIS plugins that now exist, and a humanitarian-sector reference point.

### B.1 Esri / ArcGIS AI & GeoAI

The dominant commercial GIS platform, now shipping AI broadly across its product line rather than as
one feature: 100+ pretrained GeoAI models in Living Atlas (building damage detection, road-surface
classification, feature extraction from imagery), embedded assistants per-product (Notebooks,
Solutions, Item Details, Survey123, Business Analyst, an Arcade-expression assistant), and — notably —
**MCP (Model Context Protocol) support so external AI agents on other platforms can call ArcGIS tools
directly**, alongside their own in-house agentic capability. Esri also publishes an **ArcGIS Trust
Centre** with per-assistant "Transparency Cards" (how each assistant works, human-in-the-loop design,
opt-in/opt-out data controls) as a dedicated trust/procurement artifact, separate from technical
security documentation.

**Relevant to Cartogen AI:** Esri's Trust Centre framing is aimed at exactly the buyers
`PRODUCT_TIERS.md` §4 identifies for the Enterprise vertical (defense/intelligence, large institutional
procurement) — those buyers will expect something in that shape. Cartogen AI's `SECURITY.md` is
*more* technically rigorous than what Esri's blog post describes (adversarial testing with confirmed
exploit/fix pairs, not just principles), but it's written for engineers, not procurement — there's no
short, non-technical "how does the AI behave" artifact today.

### B.2 QGIS-native AI plugins (direct competitors, same host application)

| Plugin | What it claims | How it differs from Cartogen AI |
|---|---|---|
| **GeoGPT AI Agent** (`plugins.qgis.org/plugins/qgis_ai_agent/`) | Claude-primary autonomous agent, "1308+ tools," Swedish/SCB-specific feasibility analysis, 3D visualization, QField mobile integration. Listed as **"no public version yet."** | Far larger claimed tool count (unverified — I haven't seen its code), but not yet actually released. Its listing slug (`qgis_ai_agent`) is also this project's own old internal package name — see A.3. |
| **QGIS MCP** (`plugins.qgis.org/plugins/qgis_mcp_plugin/`, open source on GitHub) | Exposes QGIS as an **MCP server** — 100+ tools reachable from Claude Desktop, Claude Code, or any other MCP client, not a bespoke in-plugin chat UI. | Architecturally distinct approach: interoperability over a standard protocol instead of a self-contained agent loop. Cartogen AI has no MCP exposure today — it's only reachable through its own dock widget and its own 5 hardcoded provider clients. |
| **GeoEdge AI** | Natural-language spatial analysis and cartography; **requires a free-or-paid cloud account** to use. | Cloud-account-gated by design — the opposite trust model from Cartogen AI's offline-first (Ollama) Community tier. Not a gap to close; a real point of differentiation worth stating explicitly rather than drifting toward. |
| **GeoAI plugin** (`plugins.qgis.org/plugins/geoai/`) | Vision-model-based: tree segmentation (DeepForest), water segmentation, Segment Anything (SAM1/2/3), semantic/instance segmentation directly on imagery. | A different capability axis entirely — automated feature *extraction* from raster imagery, not tool-calling/agentic workflow execution. `QGIS_AI_Agent_PRD.md` Phase 3 already lists "semi-automated feature extraction from imagery" as **not started** for Cartogen AI — this plugin's existence is direct evidence that gap is real and being filled by someone else in this ecosystem right now. |
| Spatial Analysis Agent, GeoPilot, Geo Knowledge AI, GeoAgent | Smaller/less-detailed listings, same general "chat to run GIS operations" category. | Not differentiated enough in public materials to compare feature-by-feature; noted for completeness. |

### B.3 UNDP RAPIDA (humanitarian sector reference point, not a QGIS plugin)

RAPIDA (Rapid Post-Crisis Integrated Digital Assessment) is UNDP's operational rapid-assessment
pipeline: within 72 hours of a crisis it combines satellite imagery (UNOSAT/Planet), AI-driven damage
detection, **seismic intensity models**, exposure databases, and engineering models into one
analytical output — plus social-media and night-light signals for broader impact estimation.

**Relevant to Cartogen AI:** this is the actual bar in the humanitarian vertical `PRODUCT_TIERS.md`
identifies as Cartogen AI's strongest claim. Cartogen AI's current damage/change tools
(`calculate_raster_change_detection`, `fetch_building_footprints`) are real and useful but narrower —
there's no seismic/hazard-intensity model integration, and no social-media/night-light signal ingestion.
This is a legitimate, sourced gap against the strongest named competitor in Cartogen's best vertical,
not a hypothetical one.

### B.4 Where Cartogen AI's claims hold up well

Grounded in this session's own verification work, not just this document's own marketing: the
adversarially-tested security posture (`SECURITY.md`'s confirmed exploit/fix table has no public
equivalent I found for any plugin above), the depth of the humanitarian tool set specifically
(JIAF/INFORM-style severity indexing, 3W/4W presence-gap analysis, P-code-carrying HDX boundaries,
Do No Harm geoprivacy obfuscation — none of the QGIS-native competitors above claim anything this
specific), and genuine offline-first execution via Ollama (GeoEdge AI's cloud-account requirement is
the opposite model).

---

## Part C — Additional feature suggestions (prioritized)

Each suggestion below is tied to a specific finding above, not a generic idea.

### Tier 1 — small, high-confidence, directly evidenced

1. **Harden the monitoring scheduler** (§A.1): minimum interval floor, concurrent-schedule cap.
   Small, contained changes to `scheduler.py`/`monitoring_tools.py`.
2. **Update `SECURITY.md`** to cover the scheduler and prompt-refiner surfaces (§A.1, §A.2) — closes
   the completeness gap, not a code change.
3. **Resolve the plugin-identity/repo-naming issue before any public submission** (§A.3) — rename the
   canonical repo, update `metadata.txt`'s `repository`/`tracker`/`homepage` in both trees.
4. ~~Expose the tool registry as an MCP server.~~ **Declined (2026-08-17) — not wanted, do not build.**
   Was the single most consequential competitive gap found (Esri moving this direction for ArcGIS, a
   dedicated `QGIS MCP` plugin already doing this for QGIS today), but the product owner does not want
   this surface added. Left here only as a record that it was considered and explicitly rejected, not
   as an open item — do not re-propose without a new explicit request.

### Tier 2 — real, moderate lift

5. **A short "Transparency Card"-style one-pager per major AI-driven action** (§B.1), mirroring what
   Esri's Trust Centre does — e.g. one page each for `execute_pyqgis_script`, `execute_read_only_sql`,
   and the destructive-action confirmation gate: what it does, what it can't do, what's confirmed by
   testing. This is a documentation deliverable, not code — cheap relative to its value in Enterprise/
   defense procurement conversations, which is exactly the audience `PRODUCT_TIERS.md` §3 identifies.
   **Shipped (2026-08-17)** as `docs/TRANSPARENCY_CARDS.md` -- three cards, every claim grounded in
   an existing `SECURITY.md` file:line reference, no new claims introduced.
6. **A damage/exposure composite tool inspired by RAPIDA's pipeline** (§B.3): compose the existing
   `calculate_raster_change_detection` and `fetch_building_footprints` with a hazard-intensity input
   (even a simple user-supplied intensity/exposure raster to start, short of building seismic modeling
   from scratch) to produce one combined damage-and-exposure severity output, in the same "thin
   composite of existing tools" pattern already used successfully for `calculate_population_in_need`
   and `population_access_gap`. **Shipped (2026-08-17)** as `calculate_damage_exposure_severity` --
   see `CHANGELOG.md`. Deliberately narrows this gap against RAPIDA rather than closing it: no
   seismic/hazard modeling, no social-media/night-light signal ingestion (that remains Tier 3 item 8
   below, still not started).
7. **Imagery-based feature extraction** (§B.2's GeoAI plugin gap, already flagged as not-started in
   the PRD): the PRD's own v1.2.0 changelog entry already correctly rejected asking a vision *LLM* for
   precise polygon coordinates as unreliable — that reasoning still holds. A dedicated segmentation
   model integration (SAM-family, matching how the competing GeoAI plugin approaches this) is a
   different, more defensible approach than what was previously rejected, and worth scoping separately
   rather than reopening the vision-LLM approach that was already correctly ruled out. **Shipped
   (2026-08-17)** as `extract_features_from_imagery` (`agent/tools/imagery_extraction.py`), per
   `docs/SAM_IMAGERY_EXTRACTION_SPEC.md` (spec-before-build discipline, matching the Prompt
   Refinement Layer). This remains a meaningfully bigger ask than any other item in this review: a
   real ML runtime (`torch`) and model checkpoint dependency, and an unverifiable-without-a-live-pass
   surface larger than any other feature shipped this session -- writing the code did not close that
   gap, only the code-structural half of it (see the spec's own updated status header for what
   still needs a live QGIS pass with a downloaded checkpoint before this is fully proven).

### Tier 3 — bigger lift / explicitly not recommended

8. **Social-media and night-light signal ingestion** (§B.3) — real capability gap against RAPIDA, but
   a genuinely large lift (new data sources, new reliability/verification questions given prompt rule
   12's anti-fabrication stance) — flag as aspirational, not near-term.
9. **Do not adopt GeoEdge AI's cloud-account-gated model** (§B.2) — noted explicitly as a
   *non-recommendation*: offline-first/BYO-key is a real, validated differentiator (§B.4), and diluting
   it to match a competitor's approach would give up more than it gains.

---

## A note on this session's own tooling

This review's research used `WebSearch` for competitor findings (kept to search-summary results after
raw page fetches for two QGIS plugin listings exceeded this session's output-size limit) and this
sandbox's shell tool (`mcp__workspace__bash`) failed 5 consecutive times this session with an identical
infrastructure error and is not expected to recover before this session ends — so this document has
**not** been propagated to the `Cartogen AI/cartogen_ai/` copy tree via `build_cartogen_ai.py`, the
same limitation noted for earlier documents this session. That sync will need to happen from an
environment with a working sandbox.

---

Sources:
- [Esri Collaborates with Microsoft to Bring ArcGIS Users New AI Enhancements](https://www.esri.com/about/newsroom/announcements/esri-collaborates-with-microsoft-to-bring-arcgis-users-new-ai-enhancements)
- [What's New in AI Assistants (February 2026) — Esri](https://www.esri.com/arcgis-blog/products/arcgis-online/geoai/whats-new-in-ai-assistants-february-2026)
- [What's new in AI assistants (June 2026) — Esri](https://www.esri.com/arcgis-blog/products/arcgis-online/geoai/whats-new-in-ai-assistants-june-2026)
- [AI in ArcGIS: building capability with trust and security — Esri UK](https://resource.esriuat.com/blog/ai-in-arcgis-built-for-trust/)
- [GeoAI in 2026: What's Real, What Isn't, and Where to Start — Blue Raster](https://blueraster.com/stories/geoai-ai-gis-in-2026/)
- [Geospatial AI — ArcGIS Architecture Center](https://architecture.arcgis.com/en/overview/introduction-to-arcgis/geospatial-ai.html)
- [GeoGPT AI Agent — QGIS Plugin Repository](https://plugins.qgis.org/plugins/qgis_ai_agent/)
- [QGIS AI Assistant — QGIS Plugin Repository](https://plugins.qgis.org/plugins/qgis_ai_assistant/)
- [GeoEdge AI — QGIS Plugin Repository](https://plugins.qgis.org/plugins/GeoEDGE_AI/)
- [GeoAI — QGIS Plugin Repository](https://plugins.qgis.org/plugins/geoai/)
- [QGIS MCP — QGIS Plugin Repository](https://plugins.qgis.org/plugins/qgis_mcp_plugin/)
- [nkarasiak/qgis-mcp — GitHub](https://github.com/nkarasiak/qgis-mcp)
- [Spatial Analysis Agent — QGIS Plugin Repository](https://plugins.qgis.org/plugins/SpatialAnalysisAgent-master/)
- [GeoPilot — QGIS Plugin Repository](https://plugins.qgis.org/plugins/GeoPilot/)
- [Geo Knowledge AI — QGIS Plugin Repository](https://plugins.qgis.org/plugins/geo_knowledge_ai/)
- [GeoAgent — QGIS Plugin Repository](https://plugins.qgis.org/plugins/geo_agent/)
- [RAPIDA — United Nations Development Programme](https://www.undp.org/crisis/rapida)
- [5 ways AI can help crisis response around the world — UNDP](https://www.undp.org/5-ways-ai-can-help-crisis-response-around-world)
- [Satellite imagery guides faster recovery in crisis zones — UNDP](https://www.undp.org/news/satellite-imagery-guides-faster-recovery-crisis-zones)
- [INFORM Severity Index — ACAPS](https://www.acaps.org/en/thematics/all-topics/inform-severity-index)
