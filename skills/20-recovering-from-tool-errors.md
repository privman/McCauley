---
name: recovering-from-tool-errors
when_to_use: "When a tool call's result has `ok: false` or an `error` field — especially if returning `{ok: false, error: \"No draft with local_id …\"}`."
description: "How to react to a structured error response from a draft-mutating tool — use the `current_local_id` from the same payload, retry, and never tell the user about it."
---

# 20 — Recovering From Tool Errors

## When to fire
A tool call returned a payload whose top-level shape includes `ok: false` and/or an `error` field. The most common case is one of the draft-mutating tools rejecting an invalid `local_id`:

```
{ "ok": false,
  "error": "No draft with local_id 'draft-001'. Current draft is 'd1'; ...",
  "current_local_id": "d1",
  "paused_local_ids": [] }
```

## Purpose
These errors are recoverable in a single tool round. The user should never see them — they're an internal mismatch between the local_id you sent and the ids the server actually keeps. Silent retry is the correct response.

## Why this happens
You can emit several tool_use blocks in one response. The server processes them in order, but you don't see any of their results until your *next* turn. So if your first call creates a draft, the server assigns it a real local_id (`d1`, `d2`, …) and returns it — but the second and third calls you already emitted in the same response still carry the placeholder id you guessed. The second one fails because the placeholder id doesn't exist in the server's stack.

This isn't a model error worth apologizing for; it's an artifact of how parallel tool calls interact with server-assigned ids.

## What to do
1. **Read the error payload.** It includes `current_local_id` and `paused_local_ids`. Those are the *real* ids the server has.
2. **Re-issue the failed tool call** with `local_id` set to `current_local_id` from that payload (unless you genuinely meant a paused draft — see below).
3. **Do not mention this to the user.** Don't say "sorry, I had a glitch", don't apologize, don't ask the user to retry. Just call the tool again with the right id and continue as if nothing happened.

## Local_ids are server-assigned, never invented
- Real local_ids look like `d1`, `d2`, `d3`. Never `draft-001`, `draft-1`, `feedback-x`, or any other format.
- The only valid sources of a local_id are: the response from a previous `update_draft` / `add_sbi` / `update_sbi` / `pivot_to_new_draft` / `resume_draft` / `list_drafts` / `submit_draft` call. Every one of those returns the draft payload, which contains the canonical `local_id`.
- If you don't know the current draft's id, call `list_drafts` once and use what it returns. Don't guess.
- When you're about to emit multiple draft-mutating tool calls in one response, use the same local_id everywhere — and if you've just called `pivot_to_new_draft` or `update_draft` on an empty stack in this same response, the second and subsequent calls won't yet know the assigned id. Either wait until the next turn (preferred), or accept that the second call will trigger this recovery path.

## Targeting a paused draft
If you genuinely meant to update a *paused* draft (`paused_local_ids` includes the one you wanted), you must call `resume_draft` first — paused drafts aren't directly mutable. Only after the resume call has succeeded should you retry the original mutation, now with the freshly-current local_id.

## Other tool errors
Any tool can return `{ok: false, error: "…"}` for reasons other than draft-id mismatch:
- `submit_draft` returns `ok: false` with reasons like "missing subject", "need at least one complete SBI" — these are about the draft content, not the local_id. Address the gap (ask the user for the missing piece, then retry).
- `load_skill` returns `{error: "no skill named …"}` — your skill name was wrong; pick a real one from the skill index.
- `resolve_entity` returning zero candidates isn't an error per se; it means the name didn't match anyone. Ask the user to clarify.

For all of these: read the error, do the right next action, and only mention the issue to the user if there's actually nothing you can do without their input.

## Avoid
- Apologizing to the user for an internal tool-id error
- Calling `list_drafts` when the error payload already told you the current id
- Inventing a different local_id ("maybe `d2` then?") — use exactly what the error payload returned
- Looping: if the same retry fails twice with the same error, stop and tell the user something specific went wrong rather than retrying indefinitely

## Interaction with other skills
- This skill is reactive — it only fires when a tool result contains `ok: false` or `error`. It doesn't have its own conversational shape; once the recovery is done, return to whichever skill was driving the current step.
- If `submit_draft` fails with a content-completeness reason ("missing subject", "need at least one complete SBI"), hand off to the relevant capture skill (04–07) to fill the gap before retrying.
