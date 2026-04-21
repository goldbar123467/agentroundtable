# Judge prompts

The orchestrator fills these templates. `{{...}}` are substituted at runtime.

---

## SCORE

```
TOPIC: {{topic}}
YOUR PERSONA: {{persona_name}}

Debaters and their assigned positions:
{{debaters_and_positions}}

Full transcript:
{{transcript}}

Pipeline-filter flags (by debater and turn):
{{pipeline_flags}}

Research dossiers (shared across the table, indexed as [S#] across all
debaters, so you can verify any citation):
{{dossiers}}

TASK: Produce a scorecard.

Output ONLY valid JSON in this exact shape — no prose before or after:

{
  "judge_id": "{{judge_id}}",
  "judge_name": "{{persona_name}}",
  "mental_model": "<one-sentence framing of the topic before scoring>",
  "scores": {
    "<debater_id>": {
      "logic":        {"score": <0-10>, "quote": "<≤15 words from transcript>", "note": "<one sentence>"},
      "evidence":     {"score": <0-10>, "quote": "...", "note": "..."},
      "rebuttal":     {"score": <0-10>, "quote": "...", "note": "..."},
      "originality":  {"score": <0-10>, "quote": "...", "note": "..."},
      "position_fit": {"score": <0-10>, "quote": "...", "note": "..."}
    }
    // ... one block per debater, keyed by their debater_id
  },
  "verdict": "<one sentence naming who you believe won and why — the harness does not use this for aggregation, it is recorded for the transcript>"
}
```

---

## DELIBERATION (optional, enabled via --deliberate flag)

```
TOPIC: {{topic}}
YOUR PERSONA: {{persona_name}}

Your prior scorecard:
{{your_scorecard}}

Other judges' scorecards (provided AFTER you submitted yours — deliberation phase):
{{other_scorecards}}

TASK: You may revise your scores if another judge surfaced something you
genuinely missed. You may NOT revise to move toward consensus. If you stand
by your original scores, say so in one sentence and emit the same JSON.

Output the same JSON shape as SCORE, with an added top-level field:
"revision_reason": "<one sentence, or 'no revision'>"
```
