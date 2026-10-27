# Day 1 runbook — click by click

Day 1 of MLASMS is **entirely Module 2: Data Processing**, so every demo below
is a data-processing tool looking at the gas-utility dataset. The students run
AWS's labs themselves; these are your 5-minute interludes on *our* data.

Keep this open on a second screen. Everything is literal: where to click, what
you'll see, what to say, and what the data actually says.

---

## 0. Thirty minutes before you walk in

```bash
cd AWS_SageMaker_Gas_Dataset
python shared/prebake_demos.py --status
```

Every row must say `yes` for the demos you plan to give. If not:

```bash
python shared/prebake_demos.py --only <the missing keys>
```

**Starting from a torn-down account?** Then, in order:

```bash
python 00-setup/create_bucket.py        # once ever - outside terraform
cd terraform && terraform apply && cd ..  # domain, reaper, budgets  (~3 min)
python 00-setup/preflight.py            # 6 checks, read-only
python shared/prebake_demos.py --all    # ~46 min, unattended
```

If the bucket already exists (it does unless someone deleted it by hand), skip
straight to `terraform apply` — the datasets survive teardown by design.

Then note these down — you'll need them in the URL bar all day:

| | |
|---|---|
**Studio domain** | `YOUR-DOMAIN-ID` |
**Studio URL** | https://YOUR-DOMAIN-ID.studio.us-east-1.sagemaker.aws |
**Bucket** | `YOUR-BUCKET-NAME` |
**Region** | us-east-1 (everything; don't let the console drift) |
**Profile** | `default` |

Both placeholders are printed by preflight, which writes them to the
gitignored `LINKS.local.md` so your real URLs are one click away:

```bash
python 00-setup/preflight.py --links
```

> ⚠️ **Check the region selector in the console says N. Virginia before every
> demo.** The console remembers the last region you used, and every artifact
> below is in us-east-1. An empty panel because you're looking at Ohio is the
> most common way this goes wrong.

---

## Get the notebooks into Studio

Do this once, before class. The repo is public, so Studio needs no credentials.

1. Studio -> **JupyterLab** -> run your space (it auto-stops after 30 min idle;
   "Run space" brings it back with your files intact).
2. **File -> New -> Terminal**, then:

```bash
git clone https://github.com/jessetop/aws_sagemaker_gas_company_demo.git
cd aws_sagemaker_gas_company_demo && git pull        # re-run just the pull on later days
```

3. The notebooks are then two clicks away in the file browser:

| Demo | Notebook |
|---|---|
3 - PySpark on Glue | `aws_sagemaker_gas_company_demo/02-processing/pyspark-deep-dive/gas_spark_deep_dive.ipynb` |
6a - Built-in algorithm (RCF) | `aws_sagemaker_gas_company_demo/04-training/builtin-rcf/rcf_builtin.ipynb` |

Nothing needs editing: both notebooks discover the bucket, account and role at
runtime. There is no copy-paste step in any demo.

---

## The spine — say this once, at the start

Draw this on the board and leave it up all day. Every demo refers back to it.

```
200M rows of raw weather        →   1.67M California station-days
(every station on earth, 10y)       joined to county gas consumption
```

> *"a gas utility's load is driven by the weather. We took every weather observation
> on earth for the last ten years, narrowed it to California's three thousand
> stations, worked out how cold each county actually got, and lined that up
> against how much gas each county burned. Everything we do today is one tool
> looking at that."*

**What the data says** — the one table to have ready:

| | mean therms | mean HDD |
|---|---|---|
| outside heating season | 35.1 M | 3.02 |
| **in** heating season | **49.6 M** | **14.24** |

41% more gas burned, against 4.7× the heating degree days.

> *"That's the product. Everything else is plumbing."*

---

## Demo 1 — Studio and the data (5 min)
**Pairs with:** Module 1 Setup · **Baked:** nothing needed

### Where to go
1. Open **https://YOUR-DOMAIN-ID.studio.us-east-1.sagemaker.aws**
2. Launch the **`roi-smdemo-gas-user`** profile → Studio opens.
3. Walk the left nav once, slowly. *"Everything we touch today is in here."*
4. New tab → **S3 console** → bucket `YOUR-BUCKET-NAME`

### What you'll see, and what to say
Open `raw/` and point at the four prefixes:

| Prefix | What it is |
|---|---|
`observations/` | NOAA GHCN daily weather — `YEAR=2015…2024` / `ELEMENT=TMAX,TMIN,PRCP` |
`stations/` | 3,241 California weather stations |
`counties/` | 58 California county centroids (US Census) |
`consumption/` | CEC therms by county × month × sector |

> *"Four public sources. Nothing proprietary, nothing simulated. Weather from
> NOAA, geography from the Census, gas consumption from the California Energy
> Commission — which publishes the gas utility by name."*

Click into `observations/YEAR=2024/` and show the `ELEMENT=` subfolders.

> *"That folder layout isn't decoration. Spark reads the directory names as
> columns, so asking for 2024 TMAX never opens the other directories. I'll
> prove that in the Spark demo."*

Then open `processed/` and show `obs_year=`/`obs_month=` partitions.

> *"Raw public data in, analytics-ready gas demand out. That arrow is the
> whole course."*

### The 30 seconds that lands with instructors
> *"One thing before we move on. Canvas bills about fifty dollars a day, and it
> keeps billing after you close the browser tab — you have to delete the app.
> We left one running after a class in June. Two hundred and two dollars. So
> there's a Lambda in this account that kills idle Canvas sessions every hour.
> If you take one thing from today's setup module: build the cost guard before
> you build the demo."*

---

## Demo 2 — Data Wrangler (5 min)
**Module 2, first tool** · **Baked:** `data`

> ⚠️ **This starts a billable Canvas session.** Data Wrangler lives inside
> Canvas now — Studio Classic is gone. Run
> `powershell -File cleanup/kill_canvas.ps1` when you're done. The reaper is a
> backstop, not permission to forget.

### Where to go
1. Studio → **Canvas** (left nav) → **Run Canvas**, wait for it to come up
2. **Data Wrangler** → **Import data** → **Amazon S3**
3. Navigate to `YOUR-BUCKET-NAME/raw/observations/`
4. Select a `YEAR=2024/ELEMENT=TMAX` parquet file → **Import**

### "Here's how you make it"
Let it profile, then point at what's *wrong* with the schema. This is the bit
that makes a room sit up, because it's real:

| Column | The trap |
|---|---|
`DATE` | a **string**, `"20240115"` — not a date |
`DATA_VALUE` | integer in **tenths of a degree C**. `390` means 39.0 °C |
`Q_FLAG` | populated **only when a reading failed** quality control |

> *"Three traps in a four-column table. Miss the tenths and every number you
> produce is plausible and ten times wrong. This is what real public data looks
> like."*

Now click **Data quality and insights report**. One click, and it's the most
impressive thing in the product — distributions, missing values, outliers, on
their data.

Add two transforms so they see the no-code loop:
- **Manage columns → Rename**: `DATA_VALUE` → `value_tenths`
- **Custom transform → Custom formula**: `value_tenths / 10`

Click **Export → Amazon S3**.

### "Hit cancel"
> *"That launches a Spark job for a few minutes. I'm not going to make you
> watch it — here's one I made earlier."*

### "Here's one I made earlier"
S3 → `processed/visual-etl/obs_year=2024/obs_month=1/` → open a Parquet file
(or show it in the Spark demo instead).

> *"Twenty-five columns. Real county names. Heating degree days computed.
> Therms joined on. Same transforms, done once, repeatable."*

**Then kill Canvas.** Out loud, so they see you do it.

---

## Demo 3 — PySpark, serverless (5 min)
**Module 2, after Data Wrangler** · **Baked:** `data`
**No EMR cluster. ~$0.07.**

### Where to go
1. Studio → **JupyterLab** → new notebook
2. Kernel: **Glue PySpark** (Glue Interactive Sessions)
3. First cell — type this and run it:

```python
%idle_timeout 15
%glue_version 4.0
%worker_type G.1X
%number_of_workers 4
```

> *"Per-second billing, no cluster. And that idle timeout is deliberate — an
> idle session still bills, and the Canvas reaper doesn't catch Glue sessions.
> It only reaps SageMaker apps."*

Then work through `02-processing/pyspark-deep-dive/gas_spark_analysis.py`.
**Three of the seven sections. These three.**

### (1) Partition pruning — 60 seconds

```python
BUCKET = "YOUR-BUCKET-NAME"
obs = spark.read.parquet(f"s3://{BUCKET}/raw/observations/")
obs.filter((obs.YEAR == 2024) & (obs.ELEMENT == "TMAX")).explain(mode="formatted")
```

**What to point at:** the `PartitionFilters` line in the plan. On the verified
run it reads:

```
PartitionFilters: [isnotnull(YEAR), isnotnull(ELEMENT), (YEAR = 2024), (ELEMENT = TMAX)]
```

And the row counts either side: **201,486,445** across all partitions.

> *"Those directories are never opened. Not read-and-discarded — never opened.
> If this said PushedFilters instead, it would have read every file and thrown
> most away. That's the difference between a folder layout and a performance
> feature."*

### (2) Broadcast vs shuffle — 90 seconds

The most transferable 90 seconds in the course. Same join, two plans:

```python
stations = spark.read.option("header","true").csv(f"s3://{BUCKET}/raw/stations/ghcnd_stations_ca.csv")
daily.hint("shuffle_merge").join(stations, "station_id").explain(mode="simple")
daily.join(F.broadcast(stations), "station_id").explain(mode="simple")
```

> *"Same answer, two completely different amounts of network traffic.
> SortMergeJoin shuffles 2.1 million rows across the cluster.
> BroadcastHashJoin ships 3,241 station rows to every executor and shuffles
> nothing. When one side of your join is small, say so."*

Spark's own threshold is worth showing — it auto-broadcasts anything under
**10 MB** (`spark.sql.autoBroadcastJoinThreshold = 10485760b`). *"The hint is
how you tell it about the cases it can't size up in advance."*

### (3) Heating sensitivity — 2 minutes. **The money shot.**

Fit `therms = a + b·HDD` for every county at once. The slope is **therms burned
per extra degree-day** — the number utility planners forecast winter load with.

**What the data actually says** (verified Glue run, 10 years, n=120 months each):

| County | correlation | therms per degree-day |
|---|---|---|
| Los Angeles | 0.877 | **9,203,284** |
| Orange | 0.898 | 3,158,101 |
| Riverside | 0.907 | 2,416,084 |
| San Diego | 0.895 | 2,228,126 |
| Santa Clara | 0.906 | 2,030,787 |
| Sacramento | 0.895 | 1,847,942 |
| **Contra Costa** | **0.667** | 1,828,716 |
| Alameda | 0.898 | 1,732,620 |
| San Bernardino | 0.879 | 1,568,868 |
| Ventura | 0.886 | 775,019 |

> *"Los Angeles burns nine million extra therms for every additional degree-day.
> Correlations of 0.88 to 0.91 — this isn't a weak signal, it's the dominant
> driver of their load."*

**The one to point at:** Contra Costa at **0.667** while its neighbours sit near
0.90. *"Something's different there — different housing stock, different
industrial mix, or a data problem. That's the question this analysis is for."*

> *"No UDF. No collect. No Python loop. The least-squares slope is just sums, so
> every county gets fitted simultaneously in one distributed aggregation. That's
> the difference between using Spark and using Spark well."*

### (3b) The bonus beat — Simpson's paradox, 60 seconds

If you have the time, this is the best thing in the whole day. Same data, two
correlations:

```
average WITHIN-county correlation :  +0.7217     (top counties 0.88 - 0.91)
POOLED correlation, all counties  :  -0.0088
```

> *"County by county, cold weather drives gas demand — the big ones correlate
> around nine tenths, and the average across all forty-seven is still north of
> seven tenths. Pool all the counties together into one correlation and it
> vanishes. Zero. Slightly negative.*
>
> *Nothing changed except the grain. Los Angeles burns more gas in a mild month
> than Alpine does in a freezing one, so the difference BETWEEN counties
> completely drowns the effect WITHIN them. Aggregate at the wrong level and
> you'll confidently report that temperature doesn't affect gas demand."*

This is Simpson's paradox on their own data, and it's also exactly why the ML
label on Day 2 is ranked within county rather than globally.

### Closing line
> *"The rest of this notebook is yours — rolling windows for cold snaps,
> overnight temperature drops, skew diagnosis, and the same query in SQL."*

Gives them a reason to keep the artifact.

---

## Demo 4 — SageMaker Processing (5 min)
**Module 2, Lab 4 territory** · **Baked:** `splits`
**Status: talk-through only** — the Processing-job wrapper isn't ported yet.

### Where to go
Open `shared/prepare_ml_data.py` in Studio's editor. No console needed.

> *"Processing is for when your transform is just code. No canvas, no cluster —
> hand SageMaker a script and a container, and it runs it on whatever size
> machine you ask for. Notice there isn't a single SageMaker import in the data
> logic. That's the point: it's a plain Python script."*

Then S3 → `ml/gas/train/`, `validation/`, `test/`.

> *"150,000 rows, 19 features, label in the first column."*

### Spend 60 seconds on the honest bit — this is the valuable part

**Group leakage.** CEC consumption is *monthly*, so every daily row inside a
county-month carries the same label.

> *"Split those rows at random and the same county-month lands on both sides of
> your split. Your model sees its test labels during training and your score is
> inflated for free. So we split by county-month group instead."*

**47% of rows have no precipitation reading.** Many GHCN stations measure
temperature but not rainfall.

> *"A null there means 'no gauge', not 'no rain'. So we impute zero AND add a
> precip_reported flag — otherwise the model can't tell a dry day from a
> missing instrument. And we do it before sampling, not after, or asking for
> 150,000 rows quietly gives you 79,000."*

---

## Demo 5 — Feature Store (5 min)
**Module 2, Feature Store section** · **Baked:** `features`

### Where to go
1. **SageMaker AI console** → left nav → **Feature Store** → **Feature groups**
2. Open **`roi-smdemo-gas-features`**

### What you'll see
The feature definitions, the record identifier, the event-time field, and the
online/offline store config.

### "Here's how you make it"
Show `03-feature-store/feature_store_ingest.py` — definitions, identifier,
event time. Then:

> *"Ingestion takes a couple of minutes, so here's the one I made earlier."*

Back to the console: click the **Offline store** S3 path and show the Parquet
sitting there.

### The line that makes it matter
> *"Right now one team computes heating degree days. Next month another team
> needs it and writes their own slightly different version — base 65 or base
> 60, mean of max and min or hourly average. Feature Store is how hdd65 gets
> defined once and consumed by everyone. And critically: the same definition at
> training time and at inference time. That's the bug it exists to prevent —
> training/serving skew."*

That last clause is the whole product. Don't skip it.

---

## Day 1 running order

| Slot | Demo | Min | Ready |
|---|---|---|---|
after Module 1 Setup | 1 — Studio + the data | 5 | ✅ |
Module 2, tool 1 | 2 — Data Wrangler | 5 | ⚠️ live-build; no saved flow |
Module 2, tool 2 | 3 — PySpark serverless | 5 | ✅ verified on Glue |
Module 2, tool 3 | 4 — Processing | 5 | ⚠️ talk-through only |
Module 2, tool 4 | 5 — Feature Store | 5 | ✅ |

Five interludes, ~25 minutes total across a 6.75-hour day. That's the right
dosage — they're punctuation, not a parallel course.

**If you're short on time, cut 4 first** (it's the only talk-through) and keep
Demo 3's heating-sensitivity section no matter what. That one is the most
utility-specific thing you will show all day.

---

## End of day

```bash
powershell -File cleanup/kill_canvas.ps1    # if you opened Canvas
python cleanup/verify_teardown.py           # must print CLEAN
```

Leave the infra up overnight — it's about $0.10/day with nothing running. Just
make sure no Canvas session, Glue session or endpoint survived.

## If something breaks mid-demo

| Symptom | Fix |
|---|---|
Empty console panel | **Check the region** — must be N. Virginia |
Glue session won't start | Check the exec role; `python 00-setup/preflight.py` |
Canvas stuck "Starting" | It takes 2-4 min; talk over it or skip to Demo 3 |
Spark cell errors | `02-processing/pyspark-deep-dive/gas_spark_analysis.py` is the proven version — copy the cell from there |
Any permissions error | `python 00-setup/preflight.py` names the exact fix |

**Always have the fallback.** `TEST_LOG.md` holds every real number from a
verified run. If a job dies on stage, switch to the log and talk through what it
produced. Nobody minds — as long as you say that's what you're doing.

---

## Teardown is now safe to run freely

The S3 bucket is **not** managed by Terraform. It used to be, which meant
`terraform destroy` deleted it — along with 720 MB of staged GHCN/CEC data, the
processed pipeline output, the ML splits and the Clarify reports. About 25
minutes and a dollar of Glue to rebuild.

```bash
cd terraform && terraform destroy     # removes domain, reaper, budgets, IAM
                                      # LEAVES the bucket and every dataset
```

To rebuild the compute afterwards: `terraform apply`. The data is still there,
so you skip straight to demoing.

The bucket only goes away if you ask for it explicitly:
```bash
powershell -File cleanup/cleanup.ps1 -IncludeBucket   # deletes the data too
```

> `prevent_destroy` was the obvious alternative and is the wrong tool — it does
> not protect the data so much as make `terraform destroy` fail outright, which
> blocks teardown of the things that actually cost money.

**One known benign drift:** `terraform plan` reports `1 to change` on the Studio
domain — AWS adds an empty `studio_web_portal_settings {}` block that Terraform
wants to remove. Cosmetic. Ignore it, or apply it when you're not about to
teach.
