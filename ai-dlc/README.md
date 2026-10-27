<!-- Module reference. Demo narration lives in ../DEMOS.md. -->

# AI-DLC — how the repo you have been using all week got written

**Demo 13.** The one demo in this repo that is not a SageMaker service.

AI-DLC is AWS's *AI-Driven Development Life Cycle*: a method in which an agent
plans the work and writes the artifacts, and a human approves or rejects at
every gate. AWS published the method in July 2025 and open-sourced the
implementation as [`awslabs/aidlc-workflows`](https://github.com/awslabs/aidlc-workflows).

It belongs in this course because **Module 6 (Managing Resources & Updates) and
Module 7 (WrapUp) are the only two decks with no demo or lab slide at all** —
and because the thing it produces is sitting in this repository.

## Why it is credible here

`.kiro/specs/sagemaker-studio-demos/requirements.md` is an AI-DLC Inception
artifact: 133 lines of glossary, user stories and EARS acceptance criteria
(`THE Dataset_Loader SHALL...`, `IF the download fails THEN retry 3 times...`).
Nobody typed it. It is the reason this repository has folders `00-` through
`10-`.

It is also **wrong**, deliberately and usefully. The spec asks for "a publicly
available tabular or image dataset of at least 100,000 samples." The class runs
on 201 million worldwide weather observations narrowed to California county
therms. A human rejected the agent's choice at the gate and the agent rebuilt
around the override. That is the method working, not failing, and it is the only
part of this demo that cannot be faked.

## The repos

| Repo | What it is |
|---|---|
[awslabs/aidlc-workflows](https://github.com/awslabs/aidlc-workflows) | the method itself — rules/steering files for Claude Code, Kiro, Q Developer, Cursor, Codex, Copilot, opencode. 5 phases, 33 stages, 14 agents, 11 workflow profiles. **This is the one to show.**
[aws-samples/sample-collaborative-ai-dlc](https://github.com/aws-samples/sample-collaborative-ai-dlc) | a human team collaborating live with several remote coding agents
[aws-samples/sample-ai-driven-development-lifecycle-platform](https://github.com/aws-samples/sample-ai-driven-development-lifecycle-platform) | a Bedrock AgentCore multi-agent app that runs the lifecycle for you. A build-and-deploy, not a five-minute demo — mention it, do not open it.

Blog post: <https://aws.amazon.com/blogs/devops/ai-driven-development-life-cycle/>

## Install (once, before class)

```powershell
irm https://github.com/awslabs/aidlc-workflows/releases/latest/download/install.ps1 | iex
```

```bash
# macOS / Linux / WSL
curl -fsSL https://github.com/awslabs/aidlc-workflows/releases/latest/download/install.sh | sh
```

Installs to `%LOCALAPPDATA%\aidlc` and registers its bin directory in **User**
PATH. Then, from the repo root:

```bash
aidlc config --harness claude   # or --harness kiro
aidlc doctor                    # must be green before you walk in
```

## Run

The unit of work, the exact prompt, and the answers to give at each human gate
are in [`unit-of-work.md`](unit-of-work.md). The captured run is in
[`transcript/`](transcript/).

## Cost

**$0 of AWS spend.** No endpoint, no training job, no Canvas app. The only demo
in the set that cannot leave something billing behind.

## Notes

This is the one genuinely **non-deterministic** demo in the repo — `/aidlc`
phrases its plan differently every run. Rehearse once, and keep the captured
transcript open in a second tab as break-glass. Read `../DEMOS.md` **Demo 13**
before giving it.

---

Demo narration: [`../DEMOS.md`](../DEMOS.md) · Click-by-click: [`../DAY3_RUNBOOK.md`](../DAY3_RUNBOOK.md)
