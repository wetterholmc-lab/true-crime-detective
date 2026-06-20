# Problem

**Stage 1 — Identify the limits of your current agency.**

## The problem

Historical court records are extraordinary primary sources — vivid, factual, often shocking — but
they're locked behind a reading experience that kills the drama. A 200-page Old Bailey transcript
dumps you into dense 19th-century legalese with no guide, no structure, and no game.

There is no agent today that can take a genuine trial transcript and turn it into a playable,
grounded mystery where you actually investigate: examine specific evidence, question the record,
form a theory, name a culprit, and then discover whether you were right.

## How it's done today — and what goes wrong

If you want to engage with a real historical case, you:
1. Search archives directly (Old Bailey Online, CourtListener, Google Books newspaper scans)
2. Read the raw transcript — dense, unindexed, hundreds of pages
3. Piece together a picture manually, hoping you noticed the key clues

What goes wrong:
- The format is hostile to casual reading — dense Victorian legalese, procedural asides, Latin
- No structure: you don't know what evidence exists until you've read everything
- No interactivity: you can't ask the record a question
- No guidance: you can't know whether a detail is significant or irrelevant
- No payoff: reading a verdict at the end of a 200-page document doesn't feel like solving it

## Why an agent makes this possible now

Three things converge:
1. **RAG grounding**: We can embed the full transcript and retrieve the exact passage relevant to
   any player question — the LLM answers from real text, not from training memory
2. **Structured extraction**: The LLM can transform a raw transcript into a clean case brief,
   cast list, and evidence index — the scaffolding the original format lacks
3. **Conversational interface**: A Telegram bot turns investigation into dialogue — natural,
   async, available anywhere

## The unique challenge: grounding

Unlike most LLM applications, this one has a *correctness constraint*: the agent must never
invent facts. A game built on hallucinations is not just broken — it's dishonest. The entire
premise is "these are the real facts of a real case."

This makes grounding the single most important engineering challenge. The solution is strict
retrieval-augmented generation: every player question triggers a semantic search over embedded
transcript chunks, and the game master is instructed to answer only from retrieved text — and
to say "the record is silent on that" when the answer isn't there.

## Who this is for

Primarily: people who find real historical crimes fascinating but find archives inaccessible.
True crime readers, history enthusiasts, people who play Sherlock Holmes or Cluedo but want
something grounded in fact. The pitch: "You're not playing a game. You're investigating a
real murder that happened 150 years ago."
