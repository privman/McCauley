"""SQLAlchemy ORM models matching design.md §4.1.

v0.1 scope: schema is the same as v1 minus a few enterprise-only columns
(see v0.1-scope.md "Simplifications"). The shape is meant to be additive, so
the v1 path doesn't require migrations beyond ADD COLUMN / new tables.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Base(DeclarativeBase):
    pass


class SubjectKind(enum.StrEnum):
    user = "user"
    unit = "unit"


class Sentiment(enum.StrEnum):
    positive = "positive"
    constructive = "constructive"
    negative = "negative"
    mixed = "mixed"


class FeedbackStatus(enum.StrEnum):
    draft = "draft"
    submitted = "submitted"
    flagged = "flagged"
    retracted = "retracted"


class Org(Base):
    __tablename__ = "orgs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    title: Mapped[str | None] = mapped_column(String(255))
    manager_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class OrgUnit(Base):
    __tablename__ = "org_units"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_unit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("org_units.id"))
    head_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class OrgSubordinate(Base):
    """Transitive closure of users.manager_id, includes self-pairs.

    See design.md §4.3 — populated by app.closure.recompute().
    """

    __tablename__ = "org_subordinates"
    ancestor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    descendant_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)


class UnitOversight(Base):
    """Units a user heads + all units above them up the parent chain."""

    __tablename__ = "unit_oversight"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("org_units.id"), primary_key=True)


class TopicTaxonomy(Base):
    __tablename__ = "topic_taxonomy"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("topic_taxonomy.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("topic_taxonomy.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("org_id", "slug"),)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)  # "provider" | "recipient"
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    language: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    channel: Mapped[str] = mapped_column(String(8), default="text", nullable=False)
    state: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class ConversationTurn(Base):
    __tablename__ = "conversation_turns"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user|assistant|tool
    content_text: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"), nullable=False)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("conversations.id"))
    provider_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    subject_kind: Mapped[SubjectKind] = mapped_column(
        Enum(SubjectKind, name="subject_kind"), nullable=False
    )
    subject_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    subject_unit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("org_units.id"))
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    topic_tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    sentiment: Mapped[Sentiment | None] = mapped_column(Enum(Sentiment, name="sentiment"))
    sentiment_score: Mapped[float | None] = mapped_column(Float)
    language: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    status: Mapped[FeedbackStatus] = mapped_column(
        Enum(FeedbackStatus, name="feedback_status"), default=FeedbackStatus.draft, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sbis: Mapped[list[SBIInstance]] = relationship(
        "SBIInstance",
        back_populates="feedback",
        cascade="all, delete-orphan",
        order_by="SBIInstance.idx",
    )


class SBIInstance(Base):
    __tablename__ = "sbi_instances"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    feedback_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("feedback.id", ondelete="CASCADE"), nullable=False
    )
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    situation: Mapped[str | None] = mapped_column(Text)
    behavior: Mapped[str | None] = mapped_column(Text)
    impact: Mapped[str | None] = mapped_column(Text)
    occurred_at_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    occurred_at_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    feedback: Mapped[Feedback] = relationship("Feedback", back_populates="sbis")

    __table_args__ = (UniqueConstraint("feedback_id", "idx"),)


class FeedbackChunk(Base):
    """One row per feedback record (see design.md §4.2).

    content = headline + first 5 SBI bodies concatenated. Written at submit
    by app.submit.write_chunk(); embedding by Voyage.
    """

    __tablename__ = "feedback_chunks"
    feedback_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("feedback.id", ondelete="CASCADE"), primary_key=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Any] = mapped_column(Vector(1024))
    # tsvector for BM25 is populated by an INSERT/UPDATE trigger from content;
    # it's intentionally NOT mapped here so SQLAlchemy doesn't try to coerce it
    # on INSERT. Retrieval queries reference it via raw SQL.


class AccessLog(Base):
    __tablename__ = "access_log"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_kind: Mapped[str | None] = mapped_column(String(32))
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
