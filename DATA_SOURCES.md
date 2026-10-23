# Data sources, licences, and attribution

Every dataset this series touches, where it comes from, and what you owe the
publisher for using it. Read this before adding a dataset or publishing
anything derived from one.

**Nothing in this repo vendors data.** `00-setup/stage_dataset.py` copies or
downloads from the publisher at setup time into *your* S3 bucket. That is partly
a size decision and partly a licensing one: the repo never redistributes anyone
else's data, so the only obligations that can attach are attribution and
share-alike on outputs you choose to publish.

---

## The spine — used by all modules

| Dataset | Publisher | Licence | Attribution required |
|---|---|---|---|
| GHCN-Daily observations | NOAA / NCEI | US Government work, public domain | Courtesy credit (below) |
| GHCN station metadata | NOAA / NCEI | US Government work, public domain | Courtesy credit |
| County gazetteer (centroids) | US Census Bureau | US Government work, public domain | Courtesy credit |
| Natural gas consumption (QFER) | California Energy Commission | California public record | Courtesy credit |

These are all government works with no licence restrictions on commercial or
educational use. Credit is good manners and good teaching, not a legal
requirement.

**Suggested credit line**

> Weather data: NOAA Global Historical Climatology Network-Daily (GHCN-Daily),
> accessed via the Registry of Open Data on AWS. County centroids: US Census
> Bureau 2020 Gazetteer. Natural gas consumption: California Energy Commission,
> Quarterly Fuel and Energy Report (QFER).

Sources:
- GHCN-Daily on AWS — `s3://noaa-ghcn-pds` ([registry entry](https://registry.opendata.aws/noaa-ghcn/))
- Census 2020 Gazetteer — <https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html>
- CEC consumption data files — <https://www.energy.ca.gov/files/energy-consumption-data-files>

---

## Optional add-on modules

### PHMSA pipeline incident data

| | |
|---|---|
| Publisher | US DOT / PHMSA |
| Licence | US Government work, public domain |
| Attribution | Courtesy credit |

Used only for the Ground Truth labelling and text-classification demos, where
the free-text incident narratives are the point. **Not** suitable as the spine:
gas distribution incidents run only ~111-139 per year nationwide (roughly 2,000
rows since 2010, and dozens if filtered to a single operator), which is far too
small for the Spark, tuning, and SHAP modules.

Source: <https://www.phmsa.dot.gov/data-and-statistics/pipeline/pipeline-incident-flagged-files>

### Carbon Mapper methane plumes

| | |
|---|---|
| Publisher | Carbon Mapper |
| Licence | **Modified CC BY-SA 4.0, non-commercial** |
| Attribution | **Required** |
| Share-alike | **Required on derivatives** |

This is the one dataset in the series with real licence conditions, so it gets
its own rules. Three things to honour:

1. **Attribution is mandatory.** Credit Carbon Mapper wherever the data or
   anything derived from it appears — notebook output, slides, README.

   > Methane plume data © Carbon Mapper, used under a modified Creative
   > Commons Attribution-ShareAlike 4.0 International Licence.
   > <https://carbonmapper.org>

2. **ShareAlike propagates.** Anything you publish that is derived from the
   plume data carries the same licence forward. If a plume-derived table,
   figure, or model output goes into a public repo, that material inherits
   BY-SA. This applies regardless of whether the use is commercial.

3. **Non-commercial.** Carbon Mapper defines non-commercial as excluding uses
   where you "derive profits... by charging a third party in exchange for
   redistributing products or services that involve your use of the Data
   Product."

   **Why this series qualifies:** the paid course content is AWS's own
   curriculum. This repo is a separate, free add-on that is demonstrated by the
   instructor and offered at no charge; nobody is charged for it, for access to
   it, or for anything derived from the plume data. The data is also never
   redistributed here — see the next point.

4. **Do not vendor the data.** Keep the fetch-at-setup pattern used by every
   other source. Students who want to reproduce the module pull plumes from
   Carbon Mapper's portal into their own account. That way the repo never
   redistributes the data and point 3 never has to be argued at all.

If the framing of this series ever changes — the repo becomes a paid product,
or plume-derived artefacts get bundled into something sold — re-check these
terms before shipping, or ask Carbon Mapper for written permission.

Sources:
- Terms of use — <https://carbonmapper.org/terms>
- Data portal — <https://carbonmapper.org/data>

---

## Adding a new dataset

Before you add one, confirm all four:

1. It is reachable without a login (ENVOY and similar portals are out — you
   cannot build a demo on a page students may not be able to open).
2. The licence permits your use, and you have written down what attribution it
   requires *here*.
3. It is fetched at setup time, not committed to this repo.
4. It is large enough for the module you are using it in. The Spark, tuning,
   and SHAP modules need six figures of rows to be honest demonstrations; a
   few thousand rows makes them theatre.
