# Day 3 runbook — click by click

Day 3 of MLASMS is **Module 6 (Managing Resources & Updates)** and **Module 7
(WrapUp)**. Neither deck has a demo or a lab slide — they are the two
slide-only modules in the course. That is a two-hour stretch with nothing on
screen but bullets, and it is where the instructor demo has to come from
somewhere else.

Demo 13 is that something. It is also the only demo in the set that costs
nothing and leaves nothing running.

---

## 0. Before you start

```bash
python shared/verify_demos.py        # habit; Demo 13 does not depend on it
aidlc doctor                         # this one it does depend on
```

`aidlc doctor` must be green. If `aidlc` is not on PATH, you never ran the
installer on this machine — see [`ai-dlc/README.md`](ai-dlc/README.md). Do it
before class, not in front of the room; it writes User PATH and the shell needs
restarting afterwards.

| | |
|---|---|
**Repo, in a terminal at the root** | the whole demo happens here |
**Second tab** | `ai-dlc/transcript/` — break glass |
**Third tab** | `.kiro/specs/sagemaker-studio-demos/requirements.md` — open it *before* you start so you are not scrolling to it on stage |

No AWS console. No region to check. Nothing bills.

---

## Demo 13 — AI-DLC (5 min)

Narration and the lines to say: [`DEMOS.md`](DEMOS.md) **Demo 13**.
The prompt and the gate answers: [`ai-dlc/unit-of-work.md`](ai-dlc/unit-of-work.md).

### 1. Frame it — 45 sec

Terminal open at the repo root, nothing running.

> *"Everything you have seen for three days — the notebooks, the Processing job,
> the tuning sweep, the pipeline — somebody had to write. AWS published an
> opinion in July 2025 about who that somebody is now. It is called AI-DLC, and
> it is open source."*

### 2. The vocabulary — 45 sec

No tool. Just say it:

- Three phases: **Inception → Construction → Operations**
- Sprints are **bolts**. Hours or days, not weeks.
- Epics are **units of work**.
- Elaboration happens in a **mob** — the team, together, in real time.
- The AI plans and drafts. A **human decides at every gate.**

> *"That last one is the whole thing. Everything else is vocabulary."*

### 3. Configure, and run it — 90 sec

```bash
aidlc config --harness claude
```

Then paste the unit of work from `ai-dlc/unit-of-work.md`. Say what you are
asking for before you hit enter:

> *"On Day 2 we trained Random Cut Forest and then stopped, because scoring it
> would have meant an endpoint billing by the hour. So we never answered the
> actual question — which counties are anomalous, and what does operations do
> about it on Monday. I am going to ask for that, and I am not going to write
> it."*

Hit enter. **Let it think on screen.** Do not narrate over the plan; let the
room read it.

The moment it stops and asks you something — threshold, scoring mechanism,
scope — that is the demo. Answer out loud, from the table in
`ai-dlc/unit-of-work.md`, so the room hears a decision rather than prompt
engineering.

🟢 **If it proposes a SageMaker endpoint, reject it on stage.** Best thirty
seconds available to you. The gate is either real or the method is marketing,
and they get to watch one close.

### 4. Hit cancel — 15 sec

🟡 Ctrl-C.

> *"This runs about twenty minutes. I am not making you watch it."*

### 5. Here's one I made earlier — 90 sec

Switch to the tab holding
`.kiro/specs/sagemaker-studio-demos/requirements.md`. Scroll the glossary, then
one acceptance criterion read verbatim:

> `THE Dataset_Loader SHALL download a publicly available tabular or image
> dataset of at least 100,000 samples`
>
> `IF the dataset download fails, THEN THE Dataset_Loader SHALL retry up to 3
> times with a 5-second delay`

Then:

> *"133 lines. A glossary, user stories, testable acceptance criteria. Nobody
> typed it. And this file is why this repo has folders 00 through 10 — the thing
> you have been running for three days came out of one of these."*

### 6. The honest close — 60 sec

This is the part that earns the demo. Point back at the dataset requirement:

> *"It asked for a public dataset of a hundred thousand samples. You spent three
> days on two hundred million weather observations narrowed down to California
> county therms. A human read that line and said no — wrong data, the client's
> own data or nothing. The agent rebuilt around the override, and that is the
> repo you cloned on Monday."*
>
> *"That is what the gate is for. 'AI plans, human decides' is not a slogan, it
> is the thing that turned a generic spec into your dataset."*

---

## Day 3 running order

| | |
|---|---|
Module 6 deck | Managing Resources & Updates — no AWS demo slot |
**Demo 13** | AI-DLC. Anywhere in Module 6 or at the top of Module 7 |
Module 7 deck | WrapUp |
Teardown, live | see below |

### Teardown, on screen, as the last thing you do

Day 3 is the right day to run this in front of them — it is the Module 6 lesson
with a bill attached.

```bash
python 07-deployment/monitor_demo_endpoint.py --delete   # if Day 2 left it up
python cleanup/verify_teardown.py
```

> *"The reaper catches Canvas. It does not catch endpoints. That is why the last
> line of every deploy script in this repo is a delete."*

---

## Break glass

| Symptom | Fix |
|---|---|
`aidlc: command not found` | PATH was set by the installer but this shell predates it. New terminal. If still missing, you never installed — go to step 5 and present the spec file alone; it still works |
`aidlc doctor` not green | Run the demo read-only: skip steps 3 and 4, open `ai-dlc/transcript/` instead and narrate it as "here's one I made earlier" |
The plan comes out differently than you rehearsed | Expected — this is the one non-deterministic demo. Narrate what it actually did. The gate is the point, not the wording |
It writes code instead of asking | You lost the gate. Ctrl-C and say so: *"that is what it looks like when you skip elaboration — and it is exactly how people end up reviewing four hundred lines they never specified"* |
No terminal, no tool, nothing works | Step 5 and step 6 alone are a complete four-minute demo. The spec file is committed and needs no tooling at all |

**Fallback:** `ai-dlc/transcript/` is a real captured run. If the live part dies,
switch to it and say so — nobody minds a recorded result, they mind being misled
about one.
