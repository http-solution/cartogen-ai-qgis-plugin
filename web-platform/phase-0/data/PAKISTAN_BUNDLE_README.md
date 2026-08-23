# Pakistan Humanitarian Phase 0 Data Bundle

This local bundle is a reproducible, public-data demonstration package for Cartogen AI Workspace Phase 0. It is not a current operational picture and must not contain beneficiary-sensitive data.

## Included layers

1. OCHA Global 3W operational presence — filter to Pakistan for country examples.
2. Pakistan subnational administrative boundaries — COD-AB.
3. Pakistan subnational population statistics — COD-PS ADM2.
4. Pakistan Healthsites — public facility points.
5. Pakistan roads — HOT/OSM road polygons sample source.
6. Pakistan humanitarian needs overview — contextual needs table.
7. Pakistan flood-event hazard data — public hazard raster resource.
8. Derived Pakistan-only 3W CSV — generated from the preserved global workbook.
## Intended workflow

> Identify Pakistan administrative areas with high population/needs context, low reported partner presence, weak facility/access context, and possible flood exposure — while displaying the age and limitations of every source.

This is a structured demonstration, not a needs assessment or operational targeting tool.

## Rebuild

```bash
python web-platform/phase-0/scripts/build_pakistan_bundle.py
```

The script retrieves the current resource URLs from the HDX API and writes `manifest.json` with:

- dataset and resource identifiers;
- metadata-modified timestamp;
- source URL;
- local filename;
- format;
- retrieved size;
- retrieval timestamp.

## Data governance

- Preserve the original files and manifest.
- Do not publish the downloaded bundle to the public repository without reviewing source licences and file sizes.
- Do not add beneficiary, household, person-level, or restricted operational data.
- Record retrieval date and resource date in every output.
- Show a freshness warning when source operational dates are old.
- Preserve OCHA/HDX, COD, Healthsites, HOT/OSM, and other source attribution.
- Do not infer that no 3W record means no assistance.
