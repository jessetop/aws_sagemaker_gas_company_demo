# Live Test Log — what was actually run against the account

Account `000000000000`, region **us-east-1**, profile `default`. Resources
named `roi-smdemo-gas-*` and tagged `Project=sagemaker-unified-studio-demos`.

> This log records only what was **executed**, with real numbers. Anything not
> listed here has not been run. The earlier results this file used to contain
> are in git history on `trunk`; they describe a different dataset in a
> different region and none of them carry over.

## 2026-10-24 — infrastructure + Module 0 + Module 1

| Step | What was tested | Result |
|---|---|---|
| Terraform | `apply` from scratch (bucket, Studio AI domain, reaper, budgets, anomaly monitor) | ✅ 19 added, 0 changed, 0 destroyed |
| Canvas reaper | Live `lambda invoke` | ✅ `{"killed": [], "kept": [], "errors": []}` |
| Canvas reaper | IAM policy simulation for `DeleteApp`/`DescribeApp` in **both** us-east-1 and us-east-2 | ✅ allowed in both |
| Canvas reaper | EventBridge `rate(1 hour)` trigger | ✅ fired unprompted before any manual invoke |
| Preflight | `00-setup/preflight.py` | ✅ 6/6 checks pass |
| 0 Setup | `stage_dataset.py --start-year 2015 --end-year 2024` | ✅ 423 objects / **720 MB**; 419 GHCN Parquet partitions + 4 lookups |
| 0 Setup | California station parse (fixed-width GHCN) | ✅ **3,241** stations, all within CA lat/lon bounds |
| 0 Setup | County centroid parse (Census gazetteer) | ✅ **58** counties; all 49 CEC county names join cleanly |
| 1 Visual ETL | Glue 4.0, 4×G.1X, full `build_pipeline()` + write | ✅ SUCCEEDED, 643 s, 0.7144 DPU-hours (**~$0.31**) |
| 1 Visual ETL | Re-run with the T2b filter-early change | ✅ SUCCEEDED, 597 s, 0.6633 DPU-hours (**~$0.29**) |
| 1 Visual ETL | Scale | ✅ **201,486,363** raw worldwide rows → **1,668,673** California station-days |
| 1 Visual ETL | Output | ✅ 1,440 objects / 69.5 MB across 120 `obs_year`/`obs_month` partitions |

### Filter-early: behaviour-preserving, but only 7% faster

Both runs were compared directly, and the T2b change is **correct**: identical
output row count (1,668,673), identical HDD-bucket histogram, and the
heating-season aggregate agreeing to ~13 significant figures (the last digits
move because float summation order changed).

The speed-up, however, was **643 s → 597 s and $0.3144 → $0.2919 — about 7%**,
not the large win the change seemed to promise. Moving a 20× data reduction
ahead of a wide shuffle *should* be dramatic. It wasn't, because the pivot was
never the bottleneck: both versions still read and scan all 201M rows off S3,
and that I/O dominates the runtime. The shuffle we optimised away was a small
share of the total.

**Keep the change** — it is strictly better and it is the right instinct. But
teach the measurement, not the instinct: the obvious optimisation returned 7%
because the real cost was somewhere else. "Profile before you optimise" lands
much harder with your own numbers than as a slogan. The honest follow-up
question for the room is "so where *did* the time go?", and the answer is S3
read throughput — which is why partition pruning (reading only the years and
elements you need) matters far more here than shuffle tuning.

### The result that matters

The dataset exists to show that gas demand tracks heating degree days. It does:

| | mean `total_therms` | mean `hdd65` |
|---|---|---|
| outside heating season | 35.1 M | 3.02 |
| **in** heating season | **49.6 M** | **14.24** |

41% more gas burned against 4.7× the heating degree days. Counties joined
correctly via nearest centroid (spot-checked Ventura, San Luis Obispo,
Calaveras, Merced, Napa against station coordinates).

HDD bucket distribution over 10 years of California station-days:

| bucket | rows |
|---|---|
| none | 680,573 |
| moderate | 474,160 |
| mild | 424,407 |
| cold | 83,684 |
| severe | 5,849 |

### Bugs found & fixed while testing (good teaching material)

1. **`ListApps` has no `LastUserActivityTimestamp`.** The Canvas reaper read
   that field off the `ListApps` response, where it does not exist — it is only
   on `DescribeApp`. Every app therefore fell back to `CreationTime` and would
   be deleted 60 minutes after launch regardless of use, i.e. **mid-demo**.
   Fixed with a per-app `DescribeApp`.
2. **The Canvas reaper swept one region.** Canvas is region-scoped and the June
   2026 overrun was in us-east-2 while the guard watched us-east-1 — the same
   wrong-region failure as the teardown script. Now sweeps a configurable list.
3. **The teardown script targeted the wrong region.** `cleanup.ps1` defaulted
   to us-east-2 and hardcoded the us-east-2 bucket after the series moved to
   us-east-1, so it deleted nothing while printing "Cleanup complete". Both
   cleanup scripts now read `demo.env` and end with a verification sweep.
4. **The pipeline shuffled the world to keep 5% of it.** `build_pipeline()` ran
   the T7 pivot (a wide shuffle) over all 201M global rows and only joined the
   California station dimension afterwards. Added T2b: a broadcast semi-join
   against the 3,241-station list *before* the shuffle. Every transform was
   correct in any order — only the **order** decided the cost. This is the best
   "why is my Spark job slow" lesson in the series.
5. **`terraform destroy` would fail on a non-empty bucket.** With 720 MB staged,
   teardown became empty-by-hand → destroy → reconcile stale state. Set
   `force_destroy`, which is safe here because every object is rebuildable from
   public sources in minutes.
6. **GHCN units and types are traps on purpose.** `DATE` is the string
   `"20240115"` (parsed with an explicit format, since a silent cast returns
   NULL under Spark's CORRECTED parser and would delete rows), and
   `DATA_VALUE` is an integer in **tenths** of a degree C — forgetting that
   gives a plausible but 10× wrong answer.
7. **CEC's `COUNTY_NUM` is not a FIPS code.** It is an alphabetical index
   (Alameda=1, Alpine=2, Amador=3) while Census FIPS runs 001, 003, 005. Joining
   on it would silently mis-assign nearly every county. We join on the
   normalised county **name** instead.
8. **CEC ships ~3 rows per county-month-sector** and pads its name fields with
   trailing whitespace. Summing is mandatory; assuming one row per group
   undercounts demand roughly 3×.

## Notes / honest caveats

- **Group structure in the label.** CEC consumption is monthly, so every daily
  row in a county-month shares one `high_demand` value. Splits must be by
  county-month, not random, or the score is inflated. This is the gas series'
  a classic leak-by-aggregation, and a better lesson than a contrived one.
- **Many GHCN stations are precipitation-only.** T8 requires both `TMAX` and
  `TMIN`, which is why 3,241 stations over 10 years yield 1.67M usable
  station-days rather than ~7M. Still far above the 100k-sample requirement.
- **Small-files on the output.** 1,440 files across 120 partitions averages
  ~48 KB each, because the default 200 shuffle partitions spread across 120
  output partitions. A `repartition("obs_year", "obs_month")` before the write
  would give one file per partition. Not yet done — it costs another Glue run
  to verify.
- **Local PySpark does not work on the authoring machine** (32-bit JRE, and
  Hadoop's Windows `winutils` shim is 64-bit only), so the transforms are
  validated on real Glue rather than locally. Glue runs cost ~$0.31 each, which
  is cheap enough to be the inner loop.

## 2026-10-26 — redeploy + ML chain

| Step | What was tested | Result |
|---|---|---|
| Terraform | `apply` from scratch, second time | ✅ 19 added; domain `YOUR-DOMAIN-ID` |
| Canvas reaper | live invoke after redeploy | ✅ `{"killed": [], "kept": [], "errors": []}` |
| 0 Setup | `stage_dataset.py 2015-2024` | ✅ 419 Parquet objects + 4 lookups |
| 1 Visual ETL | Glue 4.0, 4×G.1X | ✅ SUCCEEDED, 602 s, 0.6689 DPU-h (**~$0.29**) |
| 1 Visual ETL | row counts reproduced exactly | ✅ 201,486,363 → **1,668,673** (matches 2026-10-24) |
| — | `prepare_ml_data.py` (group split) | ✅ 150,000 rows, 5,530 county-month groups, 104,956/22,796/22,248 |
| 4 Training | SageMaker `SKLearn`, `ml.m5.large` | ✅ acc 0.8794, auc 0.9235, **145 billable sec** |

### 🔴 The model does not work, and the 0.92 is why we know

Training reported AUC **0.9235**, which was far higher than expected and
should have been treated as suspicious immediately. It was. Ablation:

| Feature set / label | AUC |
|---|---|
| all features, seasonal label | **0.9235** |
| calendar only (`obs_month`, `season_*`, `is_heating_season`) | 0.9043 |
| weather only (calendar dropped) | 0.8298 |
| **deseasonalised label** | **0.5159** |

Feature importance on the default label: `season_Winter` 0.705, `obs_month`
0.216 — the calendar is 92% of the model. Every weather column combined shares
0.079.

This is **not leakage**; the month is legitimately available at prediction time.
It is a degenerate task: gas demand is overwhelmingly seasonal, so a county's
top-quartile months *are* its winter months and "is it winter" nearly
determines the label.

Deseasonalising the label (rank within county **and** month-of-year, so the
question becomes "was this January unusual for this county's Januaries?") drops
the score to **0.5159 — a coin flip.**

**Root cause: grain mismatch.** The label is a county-MONTH aggregate while the
features are a single STATION-DAY. One day's weather at one station carries
almost no information about whether a whole county-month was anomalous.

**Fix (not yet implemented):** aggregate features to station-month to match the
label — mean/min/max temperature, total HDD, days below freezing, total
precipitation per station-month. That is also the real utility forecasting
formulation, and ~3,241 stations × 120 months leaves several hundred thousand
rows, comfortably above the 100k requirement.

Until that lands, the ML modules (3-7, 9) are honest **workflow** demos and must
not be presented as modelling results. `--no-calendar` and `--deseasonalize`
exist so the ablation can be reproduced live; see DEMO_GUIDE.md.

### Also fixed on 2026-10-26

- **`prepare_ml_data.py` dropped 47% of rows to nulls.** `precip_mm` is missing
  on 782,762 of 1,668,673 California station-days (46.9%) — many GHCN stations
  report temperature but not rainfall. Dropping half the dataset to keep one
  optional feature is the wrong trade. Now imputes 0 and adds a
  `precip_reported` indicator so the model can tell "dry day" from "no gauge".
- **`--sample` was a lie.** Sampling happened *before* the null drop, so asking
  for 150,000 rows silently returned 79,485. Reordered. Same class of mistake
  as filtering after a shuffle instead of before it.

## 2026-10-24 — teardown

| Step | What was tested | Result |
|---|---|---|
| Cleanup | `cleanup.ps1` (Glue job, apps, endpoints; derived data) | ✅ Glue job removed; sweep reported the one check it could not run |
| Teardown | `terraform destroy` | ✅ **19 destroyed**; bucket gone in 2 s despite 423 objects (`force_destroy`) |
| Verify | `cleanup/verify_teardown.py` across us-east-1 + us-east-2 | ✅ **CLEAN** — nothing billable, and every check ran |
| Verify | bucket / domains / reaper / Glue jobs / budgets | ✅ all gone; pre-existing account budget untouched |
| Verify | `roi-smdemo-exec-role` | ✅ survives by design (predates this project; Terraform only references it) |

**Three EMR Serverless applications had survived every previous teardown** and
were found by the new multi-region sweep:

| region | application | created |
|---|---|---|
| us-east-1 | `sm-canvas-data-wrangler-emr-app-roi-smdemo-user` | 2026-07-07 |
| us-east-2 | `sm-canvas-data-wrangler-emr-app-default-20260622T122252` | 2026-06-22 |
| us-east-2 | a leftover EMR Serverless app (STOPPED) | — |

None were billing — no pre-initialised capacity — but they persisted for months
because the cleanup script only ever ran against one region and matched
`<prefix>-emr` by exact name. Opening Data Wrangler or Canvas auto-provisions an
app called `sm-canvas-data-wrangler-emr-app-<user-profile>`, which matching on
our own prefix can never find. All three are now removed.

Still present and harmless (metadata only, no cost): earlier experiments and
model-package groups in both regions, plus two stray Canvas AutoML experiments.
Worth clearing before class purely so the console you demo from looks tidy.

## Not yet run

Modules 2–10 (EMR, Feature Store, training, tuning, Clarify/Debugger/Ground
Truth, deployment, pipelines, Autopilot, custom container) still carried the old
schema and have **not** been ported or executed against the gas dataset.
