# Scenarios

**Stage 3 — Concrete end-to-end walkthroughs.** Real inputs, expected outputs.
These become the test checklist for stage 8.

Source cases are from Old Bailey Online (public domain). Verdicts are real.

---

## Happy path: New case arrival

**Case used:** R v. Franz Müller (1864) — first murder on an English railway.

1. Player has no active case. They type anything or the cron fires.
2. Bot pushes:
   ```
   🔎 A new case has crossed your desk, Detective.

   THE PEOPLE v. FRANZ MÜLLER
   Old Bailey, October 1864

   Thomas Briggs, a bank clerk, was found dead on the North London Railway —
   his skull fractured, his gold watch chain missing. A hat found in the carriage
   did not belong to him.

   The accused: Franz Müller, a German tailor, 24 years old, who had already
   boarded a ship to New York before the body was identified.

   Evidence on file:
     • [1] Müller's hat (left at scene)
     • [2] Briggs's hat (found with Müller in New York)
     • [3] Jeweller's testimony
     • [4] Ship's passenger manifest
     • [5] Cab driver's statement

   What would you like to do?
   /examine 1  — examine a piece of evidence
   /ask — ask a question about the case
   /accuse — name your suspect
   /hint — request a nudge
   /record — your detective record
   ```

**Expected:** Clean brief, evidence list with numbered items, command menu.

---

## Happy path: Examine evidence

1. Player sends `/examine 2` (Briggs's hat found with Müller).
2. Bot retrieves the relevant transcript chunk and replies:
   ```
   📁 EVIDENCE ITEM 2: Briggs's Hat

   From the trial record:
   "The hat produced was identified by Mr Briggs's son as belonging to his father.
   It was smaller in the crown than the hat left behind in the carriage. The
   prisoner had it with him when arrested aboard the Victoria in New York harbour."

   The detective noted: this hat was in Müller's possession 3,000 miles from
   the scene.
   ```

**Expected:** Quote from the actual transcript. No invented details. A brief atmospheric
frame (in italics or a header) that doesn't add facts — just context.

---

## Happy path: Free-form question

1. Player asks: "Did Müller have a motive?"
2. System embeds the question, retrieves top-5 chunks, passes to game master.
3. Bot replies:
   ```
   The trial record doesn't speak explicitly to motive, Detective. But the
   testimony of Mr Death, the jeweller of Cheapside, may interest you:

   "The prisoner came to my shop on the evening of the 9th July and offered
   for sale a gold watch chain. He said it was his own property."

   The chain was later identified as belonging to Thomas Briggs.
   ```

**Expected:** Grounded in retrieved text. "The record doesn't speak to X" when
the chunk doesn't contain the answer. Quotes where possible.

---

## Happy path: Making an accusation

1. Player sends `/accuse`.
2. Bot replies:
   ```
   ⚖️  State your accusation, Detective.

   Who do you believe is responsible? And do you believe they are guilty or not guilty?

   Example: "I accuse Franz Müller. Guilty."
   ```
3. Player replies: "Franz Müller. Guilty."
4. Bot extracts name and verdict, scores it, reveals:
   ```
   ✅ YOUR ACCUSATION: Franz Müller — Guilty

   THE REAL VERDICT:
   Franz Müller was found GUILTY by the jury on 27 October 1864. He was
   executed on 14 November 1864 at Newgate Prison.

   The case turned on the hat, the stolen watch chain, and the jeweller's
   testimony. The defence argued the evidence was circumstantial — but the
   jury was not persuaded.

   🏅 DETECTIVE RECORD: 1 case solved. Accuracy: 100%.

   A new case will arrive shortly, Detective.
   ```

**Expected:** Score shown clearly. Real verdict and brief explanation. Record updated.
Next case offered.

---

## Happy path: Hint nudge

1. Player has been inactive for 24 hours with no accusation.
2. Bot sends unprompted:
   ```
   🕵️ Still on the Müller case, Detective?

   A nudge: consider the hat left behind at the scene. Why would a murderer
   leave his own hat — and take the victim's?
   ```
3. This hint is drawn from evidence in the record, not invented.

**Expected:** Hint points toward real evidence. Doesn't give away the verdict.
Maximum 3 hints per case before offering to close.

---

## Edge case: Question with no answer in the record

1. Player asks: "What happened to Müller's family after the execution?"
2. Retrieval finds no relevant chunks.
3. Bot replies:
   ```
   The trial record is silent on that, Detective. What we have is the testimony
   from the courtroom — events after the verdict fall outside the transcript.
   ```

**Expected:** Clear, honest boundary. No invention.

---

## Edge case: Player tries to get the verdict early

1. Player asks: "Just tell me — did he do it?"
2. Bot replies:
   ```
   That's for you to decide, Detective. The facts are in the record.
   When you're ready, use /accuse.
   ```

**Expected:** In-character refusal. No spoiler.

---

## Edge case: Player accuses the wrong person

**Case:** R v. Adelaide Bartlett (1886) — chloroform poisoning.

1. Player accuses "Edwin Bartlett" (the victim, not the accused).
2. Bot extracts name, finds it doesn't match any accused person in the case.
3. Bot replies:
   ```
   ❌ YOUR ACCUSATION: Edwin Bartlett — Guilty

   Edwin Bartlett was the victim in this case, not a suspect. The accused
   before the court was Adelaide Bartlett.

   THE REAL VERDICT:
   Adelaide Bartlett was found NOT GUILTY on 17 April 1886, to considerable
   public astonishment. The cause of death — chloroform administered in a
   lethal quantity — was established; how it was administered remained unclear.

   🔍 DETECTIVE RECORD: 0/1 correct.
   ```

**Expected:** Handles wrong name gracefully. Still reveals verdict. Still updates record.

---

## Edge case: All cases completed

1. Player types anything; all available cases are played.
2. Bot replies:
   ```
   🗂 You've cleared the case file, Detective.

   Cases investigated: 5
   Correct verdicts: 4/5

   No new cases are loaded yet. Check back soon — or type /record to review
   your solved cases.
   ```

**Expected:** Clear message. No crash. Record shown.

---

## Done = all scenarios pass

When every scenario behaves as written, the core game loop is working. Add new scenarios
here as edge cases are discovered during testing.
