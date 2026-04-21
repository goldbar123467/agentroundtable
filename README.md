# agentroundtable

A roundtable harness for structured LLM debates.

- **4 debaters** — each gets the same `role.md` and `prompts.md`. A position
  is assigned at runtime.
- **3 judges** — each gets their own `role.md` and `prompts.md` and emits a
  structured JSON scorecard.
- **Karpathy guidelines** — vendored as a skill from
  [forrestchang/andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills)
  and injected as a system-prompt prefix for every debater and judge call, so
  research and arguing follow the same anti-slop discipline.
- **Standard pipeline filter** — every turn is annotated (citation density,
  slop-phrase hits, word count). Judges see the flags and the aggregator
  surfaces outlier judges via per-dimension z-scores.
- **OpenRouter** for models (any slug), **Brave Search** for live research.

The goal: run the planning/design/debate loop automatically so you can focus
on the build loop that follows.

---

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# then edit .env with your OPENROUTER_API_KEY and BRAVE_API_KEY
```

## Run

```bash
# Auto-generate four positions for the topic.
python -m src.main --topic "Should municipal broadband replace ISP monopolies?"

# Or pin positions explicitly via YAML:
python -m src.main \
  --topic "Should municipal broadband replace ISP monopolies?" \
  --positions my_positions.yaml
```

`my_positions.yaml`:

```yaml
D1: "Municipal broadband should replace ISP monopolies in underserved markets."
D2: "Municipal broadband is a policy trap and will underperform market ISPs."
D3: "A hybrid open-access fiber model outperforms both pure public and pure private."
D4: "The framing is wrong — wireless spectrum reform is the real lever."
```

## What you get

Artifacts land in `transcripts/<timestamp>-<topic-slug>/`:

| File              | Contents                                              |
|-------------------|-------------------------------------------------------|
| `transcript.md`   | Human-readable debate + aggregated scoreboard         |
| `transcript.json` | Every turn + pipeline flags                           |
| `scorecard.json`  | All three judge cards + aggregate + outlier flags     |
| `dossiers.json`   | Raw Brave results + each debater's research memo      |

## How it works

```
   ┌─────────────┐
   │  --topic    │
   └──────┬──────┘
          ▼
   ┌──────────────┐   Brave Search × 4 debaters (parallel)
   │  research    │   → dossier + research memo (Karpathy skill applied)
   └──────┬───────┘
          ▼
   ┌──────────────┐   opening → rebuttal → closing
   │  rounds      │   later speakers in a round see earlier turns
   └──────┬───────┘
          ▼ pipeline.analyze_turn → citation + slop flags
   ┌──────────────┐
   │  judging     │   3 judges (parallel) → JSON scorecards
   └──────┬───────┘
          ▼ pipeline.aggregate_scores → mean/median/outliers
   ┌──────────────┐
   │  artifacts   │
   └──────────────┘
```

## Configuration

`config.yaml` is the only knob worth tuning day-to-day. Swap models, adjust
slop phrases, change round order, tune the outlier-z threshold.

Models are OpenRouter slugs — see https://openrouter.ai/models. The defaults
pick one model from each major provider so the panel isn't monocultural.

## Layout

```
agentroundtable/
├── config.yaml              # debaters, judges, pipeline thresholds
├── roles/
│   ├── debater/{role,prompts}.md    # same for all 4 debaters
│   └── judge/{role,prompts}.md      # same for all 3 judges
├── skills/
│   └── karpathy-guidelines.md       # injected into every LLM call
├── src/
│   ├── openrouter.py   # thin chat client
│   ├── brave.py        # thin search client
│   ├── skills.py       # skill loader
│   ├── pipeline.py     # filter + aggregation
│   ├── debater.py
│   ├── judge.py
│   ├── orchestrator.py # full debate loop
│   └── main.py         # CLI
└── tests/              # pytest smoke tests (no network)
```

## Tests

```bash
pytest -q
```

The tests cover the pipeline filter and prompt-template parsing. They do not
hit OpenRouter or Brave.

## Extending

- **New skill** — drop `skills/<name>.md` and add its stem to the `skills`
  list on a `Debater` or `Judge`.
- **More debaters or judges** — add entries under `debaters:` / `judges:` in
  `config.yaml`. The orchestrator handles N.
- **Deliberation round** — the judge `prompts.md` includes a `DELIBERATION`
  template; wire it into `Orchestrator.judge_phase` if you want a second
  pass where judges may revise after reading peers' cards.

## Notes on intent

This harness is deliberately biased against LLM slop. The filter flags
citation-light arguments and generic-phrase density; the judge rubric
includes an `originality` dimension that specifically penalizes AI-flavored
filler. The more rigor you want, raise `min_citations_per_argument` and
lower `slop_warn_threshold_per_1k` in `config.yaml`.
