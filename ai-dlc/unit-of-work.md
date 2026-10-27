<!-- The thing you type on stage. Narration: ../DEMOS.md Demo 13. -->

# The unit of work

One *unit of work* (AI-DLC's replacement for "epic"), sized for one *bolt*
(its replacement for "sprint" — hours, not weeks).

It is chosen so the room already knows why it matters: **Demo 6a stops before
scoring.** Random Cut Forest trains, and then we stop, because scoring would
mean an endpoint billing by the hour. So the obvious next question — *which
counties are actually anomalous, and what does operations do on Monday?* — has
been left hanging on purpose since Day 2. Demo 13 answers it without writing
the code.

## The prompt

Paste this verbatim:

```text
/aidlc Build a daily gas-load anomaly triage report for a California gas
utility. Score the most recent 30 days of county station-days with the Random
Cut Forest model already trained in 04-training/builtin-rcf, without standing
up a SageMaker endpoint. Emit a ranked CSV plus a one-paragraph plain-English
verdict naming the counties whose therms deviate most from what their heating
degree days predict. The alert threshold must be explicit and defensible, not
a magic number.
```

Three things in that prompt are deliberate, and worth saying out loud when the
agent starts asking about them:

1. **"without standing up an endpoint"** — a cost constraint stated as a
   requirement. Watch where it surfaces in the plan.
2. **"explicit and defensible, not a magic number"** — `launch_rcf.py` already
   notes that RCF scores have no absolute scale, so any threshold is a policy
   choice. The agent cannot resolve that one. It has to ask.
3. **"what operations does on Monday"** — the output has a reader. Specs written
   without one are how you get 133 lines of correct, useless acceptance
   criteria.

## The gates

The pause is the demo. When it asks, answer short and out loud so the room hears
a decision being made rather than a prompt being engineered:

| It asks about | Say |
|---|---|
scoring mechanism | Batch Transform, not an endpoint — it is the same container, billed per job instead of per hour
the threshold | mean + 3·σ of the score distribution, stated in the report, and the report must say how many counties that flagged
scope | the 18 features already in `shared/prepare_ml_data.py`. Do not invent new ones
the label | there is none. This is unsupervised — `high_demand` is dropped, same as Demo 6a

If it proposes an endpoint anyway, **reject it on stage.** That is the single
most valuable thirty seconds of the demo: the method is only worth anything if
the human gate is real, and the room needs to watch one close.

## What good looks like

A plan, a spec with acceptance criteria you could hand to a contractor, and a
stop. Not code. If it has started writing Python inside the five minutes, you
have skipped the part that makes this different from autocomplete.
