# Debater prompts

The orchestrator fills these templates per turn. `{{...}}` are substituted at
runtime.

---

## RESEARCH

```
TOPIC: {{topic}}
POSITION ASSIGNED TO YOU: {{position}}
YOUR PERSONA: {{persona_name}}

Below is your Brave Search dossier. Each entry has an index [S#], a URL, a
title, and a snippet.

DOSSIER:
{{dossier}}

TASK: Produce a research memo you will use during the debate. Requirements:

1. Identify the 3–5 STRONGEST factual claims you can cite from this dossier
   in support of your assigned position. Use [S#] tags.
2. Identify the 2–3 STRONGEST factual claims your opponents will likely cite
   against you, and your best responses to each.
3. Flag any [S#] entries you consider weak, off-topic, or contradictory —
   do not cite those in the debate.

Output format:

## Thesis (one sentence)
...

## Top claims for our side
- Claim — [S#] — one-line reasoning

## Anticipated opposition + responses
- Opposition claim — [S#] — your counter

## Dossier entries to AVOID citing
- [S#] — reason

Budget: 500 words. No preamble.
```

---

## OPENING

```
TOPIC: {{topic}}
YOUR POSITION: {{position}}
YOUR PERSONA: {{persona_name}}
OTHER DEBATERS AND THEIR POSITIONS: {{other_debaters}}

Your research memo:
{{research_memo}}

Dossier (for citations — use [S#]):
{{dossier}}

TASK: Deliver your OPENING statement. You are going first in the assigned
order; later debaters will respond to you, so plant claims they must answer.

- Open with your thesis in one sentence. No throat-clearing.
- 3 supporting claims. Each must cite at least one [S#].
- End with the one question you most want opponents to have to answer.
- Word budget: {{word_budget}}.
```

---

## REBUTTAL

```
TOPIC: {{topic}}
YOUR POSITION: {{position}}
YOUR PERSONA: {{persona_name}}

Transcript so far (openings + any prior rebuttals):
{{transcript}}

Your research memo:
{{research_memo}}

Dossier (for citations — use [S#]):
{{dossier}}

TASK: Deliver your REBUTTAL.

- Name the single strongest opponent claim against your position and steelman
  it in one sentence.
- Attack it with cited evidence. Use [S#].
- Pick ONE additional opponent claim to dismantle.
- Concede anything you must concede, explicitly, and explain why it does not
  decide the match.
- Do NOT restate your opening. Judges already read it.
- Word budget: {{word_budget}}.
```

---

## CLOSING

```
TOPIC: {{topic}}
YOUR POSITION: {{position}}
YOUR PERSONA: {{persona_name}}

Full transcript (openings + rebuttals):
{{transcript}}

Your research memo:
{{research_memo}}

Dossier (for citations — use [S#]):
{{dossier}}

TASK: Deliver your CLOSING.

- Structure: "The panel should find for {{position}} because (1) ... (2) ...
  (3) ..." — three crisp reasons, each tied to specific cited evidence.
- One sentence explaining what your opponents FAILED to rebut.
- No new arguments. No new sources.
- Word budget: {{word_budget}}.
```
