---
name: add-another-example
when_to_use: After one SBI is captured and confirmed, decide whether to probe for a second example supporting the same headline point.
description: When and how to ask for additional SBI examples that strengthen the same headline; when one is enough.
---

# 07a — Add Another Example

## When to fire
A piece of feedback has just had an SBI confirmed (after skill 07). Before moving on, decide whether the point would be strengthened by capturing a second or third example for the same headline.

## Purpose
A feedback record can have 1..N SBI examples — the data model and tools (`add_sbi`, `update_sbi`) explicitly support this. Two or three examples turn a single observation into a credible pattern, but a single specific dated example is often enough.

## Probe for another when
- The captured SBI is weak or generic — a second helps clarify what the provider actually means.
- The headline claims a *pattern* ("she does this all the time") but only one instance was given.
- The headline is broad ("Priya communicates well across teams") and one example only proves it for one context.

## One is enough when
- The single example is specific, dated, and complete (clear S, B, I).
- The provider signals they're done ("that's the main one", "that's what I wanted to share").
- The headline is narrow enough that one instance proves the point ("Priya handled the X incident calmly").

## Phrasing

> Is there another time this came up?

> Can you think of a second example, or is this the main one?

> Got another instance, or shall we move on?

If they offer a second, use `add_sbi` to start a new SBI on the same draft, then return to skill 04 to anchor and run through 05–07 again. Stop at three; more rarely adds signal.

## Avoid
- Asking for more when the first example is already strong and specific
- Repeating the same elicitation pattern verbatim — vary the angle
- Treating "I think that's it" as an invitation to push for another

## Interaction with other skills
- After each additional SBI is confirmed via skill 07, return here to decide whether to add a third or proceed
- Hand off to skill 17 (confirmation + bias check) once all SBIs are captured for this point
- Then to skill 16 (multi-feedback sequencing) to decide whether the provider has another *record* to give
