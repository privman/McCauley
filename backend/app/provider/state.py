"""Provider-side draft state held in the orchestrator (design.md §5).

A `DraftStack` is the working set: one `current` draft plus a LIFO of
paused drafts. Drafts are keyed by a synthetic `local_id` the LLM uses in
tool calls; the orchestrator translates that to a real Feedback row when
the draft is submitted.

This module is pure data + transitions. Persistence happens in the
orchestrator on submit.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class SBIDraft:
    idx: int
    situation: str | None = None
    behavior: str | None = None
    impact: str | None = None
    occurred_at: str | None = None  # free-text from the user; structured at submit

    @property
    def complete(self) -> bool:
        return bool(self.situation and self.behavior and self.impact)


@dataclass
class FeedbackDraft:
    local_id: str  # short id the LLM sees, e.g. "d1"
    subject_kind: Literal["user", "unit"] | None = None
    subject_id: uuid.UUID | None = None
    subject_name: str | None = None  # for display only
    headline: str | None = None
    is_anonymous: bool = False
    sbis: list[SBIDraft] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """True if no real information has been captured yet.

        `is_anonymous` defaults to False on every draft and so isn't a
        signal of user intent; we ignore it for the empty check.
        """
        if self.subject_kind is not None or self.headline:
            return False
        return not any(s.situation or s.behavior or s.impact or s.occurred_at for s in self.sbis)

    def add_sbi(self) -> SBIDraft:
        sbi = SBIDraft(idx=len(self.sbis))
        self.sbis.append(sbi)
        return sbi

    def update_sbi(self, idx: int, field_name: str, value: str) -> None:
        if idx < 0 or idx >= len(self.sbis):
            raise IndexError(f"sbi_idx {idx} out of range")
        if field_name not in {"situation", "behavior", "impact", "occurred_at"}:
            raise ValueError(f"unknown sbi field {field_name}")
        setattr(self.sbis[idx], field_name, value)

    def ready_to_submit(self) -> tuple[bool, str | None]:
        if self.subject_kind is None or self.subject_id is None:
            return False, "missing subject"
        if not self.headline:
            return False, "missing headline"
        if not self.sbis or not any(s.complete for s in self.sbis):
            return False, "need at least one complete SBI (situation + behavior + impact)"
        return True, None

    def to_payload(self) -> dict[str, object]:
        return {
            "local_id": self.local_id,
            "is_empty": self.is_empty,
            "subject": (
                {
                    "kind": self.subject_kind,
                    "id": str(self.subject_id) if self.subject_id else None,
                    "name": self.subject_name,
                }
                if self.subject_kind
                else None
            ),
            "headline": self.headline,
            "is_anonymous": self.is_anonymous,
            "sbis": [
                {
                    "idx": s.idx,
                    "situation": s.situation,
                    "behavior": s.behavior,
                    "impact": s.impact,
                    "occurred_at": s.occurred_at,
                    "complete": s.complete,
                }
                for s in self.sbis
            ],
        }


@dataclass
class DraftStack:
    current: FeedbackDraft | None = None
    paused: list[FeedbackDraft] = field(default_factory=list)
    _counter: int = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"d{self._counter}"

    def new_draft(self) -> FeedbackDraft:
        draft = FeedbackDraft(local_id=self._next_id())
        if self.current is not None:
            self.paused.append(self.current)
        self.current = draft
        return draft

    def pivot(self) -> FeedbackDraft:
        return self.new_draft()

    def resume(self, local_id: str) -> FeedbackDraft:
        for i, d in enumerate(self.paused):
            if d.local_id == local_id:
                target = self.paused.pop(i)
                if self.current is not None:
                    self.paused.append(self.current)
                self.current = target
                return target
        if self.current and self.current.local_id == local_id:
            return self.current
        raise KeyError(f"no draft with local_id {local_id}")

    def get(self, local_id: str) -> FeedbackDraft:
        if self.current and self.current.local_id == local_id:
            return self.current
        for d in self.paused:
            if d.local_id == local_id:
                return d
        raise KeyError(f"no draft with local_id {local_id}")

    def remove(self, local_id: str) -> None:
        if self.current and self.current.local_id == local_id:
            self.current = self.paused.pop() if self.paused else None
            return
        self.paused = [d for d in self.paused if d.local_id != local_id]

    def to_payload(self) -> dict[str, object]:
        return {
            "current": self.current.to_payload() if self.current else None,
            "paused": [d.to_payload() for d in self.paused],
        }
