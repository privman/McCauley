---
name: anonymity-considerations
when_to_use: When the user toggles anonymity on, asks about it, or seems to be holding back because of fear of attribution.
description: How to handle anonymous feedback gracefully — when to suggest it, what tradeoffs to surface.
---

# Anonymity considerations

Anonymity is per-conversation but can be different per-draft within a session. Default is off.

## When the user is holding back

If a user hedges ("I don't want to make it weird with Priya…", "I don't know if I should say this"), gently surface the anonymity option:

> *"Would it help to mark this one anonymous? The recipient sees the feedback but not who it came from."*

Don't push. Some users prefer to own their feedback even when it's hard.

## What anonymous changes

- Provider's name is not shown to the recipient or in any retrieval result.
- The feedback still goes through the same ACL and shows up in the recipient's chat or reports — they just see "Anonymous" as the source.
- Anonymous feedback gets stricter screening downstream (out of scope for v0.1; flag in the captured record so v1 can apply it).

## What anonymity does NOT do

- It doesn't change what's *in* the feedback. If the user writes "as the only person on the Slack thread last Thursday, I saw…", they've identified themselves anyway. Surface this if it's obvious: *"This phrasing might give away who you are — want to reword it?"*
- It doesn't shield the user from social consequences if recipients guess (e.g. only one person was in the room).

## Don't default to anonymous

Named feedback is more useful: it can be followed up on, recipients can ask clarifying questions, and the social commitment of attaching one's name often produces more measured wording. Reserve anonymity for situations where the user genuinely needs it.
