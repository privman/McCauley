"""initial schema (design.md §4.1, §4.2, §4.3)

Revision ID: 0001
Revises:
Create Date: 2026-05-22

"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    subject_kind = sa.Enum("user", "unit", name="subject_kind")
    sentiment = sa.Enum("positive", "constructive", "negative", "mixed", name="sentiment")
    feedback_status = sa.Enum(
        "draft", "submitted", "flagged", "retracted", name="feedback_status"
    )

    op.create_table(
        "orgs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("external_id", sa.String(255)),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("title", sa.String(255)),
        sa.Column("manager_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_users_org_id", "users", ["org_id"])
    op.create_index("ix_users_manager_id", "users", ["manager_id"])
    # Trigram index for fuzzy name match (entity resolver).
    op.execute("CREATE INDEX ix_users_name_trgm ON users USING gin (name gin_trgm_ops)")

    op.create_table(
        "org_units",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("parent_unit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("org_units.id")),
        sa.Column("head_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
    )
    op.execute("CREATE INDEX ix_org_units_name_trgm ON org_units USING gin (name gin_trgm_ops)")

    op.create_table(
        "org_subordinates",
        sa.Column(
            "ancestor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            primary_key=True,
        ),
        sa.Column(
            "descendant_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            primary_key=True,
        ),
    )
    op.create_index(
        "ix_org_subordinates_descendant", "org_subordinates", ["descendant_user_id"]
    )

    op.create_table(
        "unit_oversight",
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True
        ),
        sa.Column(
            "unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org_units.id"),
            primary_key=True,
        ),
    )
    op.create_index("ix_unit_oversight_unit", "unit_oversight", ["unit_id"])

    op.create_table(
        "topic_taxonomy",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column(
            "parent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("topic_taxonomy.id")
        ),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "merged_into_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("topic_taxonomy.id"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("org_id", "slug"),
    )

    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("language", sa.String(8), nullable=False, server_default="en"),
        sa.Column("channel", sa.String(8), nullable=False, server_default="text"),
        sa.Column("state", postgresql.JSONB, nullable=False, server_default="{}"),
    )

    op.create_table(
        "conversation_turns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idx", sa.Integer, nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content_text", sa.Text),
        sa.Column("payload", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_conversation_turns_conversation_idx",
        "conversation_turns",
        ["conversation_id", "idx"],
    )

    op.create_table(
        "feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversations.id")),
        sa.Column("provider_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("is_anonymous", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("subject_kind", subject_kind, nullable=False),
        sa.Column("subject_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("subject_unit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("org_units.id")),
        sa.Column("headline", sa.Text, nullable=False),
        sa.Column(
            "topic_tags",
            postgresql.ARRAY(sa.String),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("sentiment", sentiment),
        sa.Column("sentiment_score", sa.Float),
        sa.Column("language", sa.String(8), nullable=False, server_default="en"),
        sa.Column("status", feedback_status, nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_feedback_subject_user", "feedback", ["subject_user_id"])
    op.create_index("ix_feedback_subject_unit", "feedback", ["subject_unit_id"])
    op.create_index("ix_feedback_status", "feedback", ["status"])
    op.execute("CREATE INDEX ix_feedback_topic_tags ON feedback USING gin (topic_tags)")

    op.create_table(
        "sbi_instances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "feedback_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("feedback.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idx", sa.Integer, nullable=False),
        sa.Column("situation", sa.Text),
        sa.Column("behavior", sa.Text),
        sa.Column("impact", sa.Text),
        sa.Column("occurred_at_start", sa.DateTime(timezone=True)),
        sa.Column("occurred_at_end", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("feedback_id", "idx"),
    )

    op.create_table(
        "feedback_chunks",
        sa.Column(
            "feedback_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("feedback.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("embedding", Vector(1024)),
        sa.Column("tsv", postgresql.TSVECTOR),
    )
    op.execute(
        "CREATE INDEX ix_feedback_chunks_tsv ON feedback_chunks USING gin (tsv)"
    )
    op.execute(
        "CREATE INDEX ix_feedback_chunks_embedding "
        "ON feedback_chunks USING hnsw (embedding vector_cosine_ops)"
    )
    # Keep tsv in sync with content via a simple trigger.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION feedback_chunks_tsv_update() RETURNS trigger AS $$
        BEGIN
          NEW.tsv := to_tsvector('english', coalesce(NEW.content, ''));
          RETURN NEW;
        END
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_feedback_chunks_tsv
        BEFORE INSERT OR UPDATE ON feedback_chunks
        FOR EACH ROW EXECUTE FUNCTION feedback_chunks_tsv_update();
        """
    )

    op.create_table(
        "access_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_kind", sa.String(32)),
        sa.Column("target_id", postgresql.UUID(as_uuid=True)),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("payload", postgresql.JSONB),
    )
    op.create_index("ix_access_log_user_at", "access_log", ["user_id", "at"])

    # feedback_visible_to_me view (design.md §4.3)
    op.execute(
        """
        CREATE VIEW feedback_visible_to_me AS
        SELECT f.*
        FROM feedback f
        LEFT JOIN org_subordinates os
          ON os.descendant_user_id = f.subject_user_id
         AND os.ancestor_user_id   = current_setting('app.current_user_id', true)::uuid
        LEFT JOIN unit_oversight uo
          ON uo.unit_id = f.subject_unit_id
         AND uo.user_id = current_setting('app.current_user_id', true)::uuid
        WHERE f.status = 'submitted'
          AND (
            os.ancestor_user_id IS NOT NULL
            OR uo.user_id IS NOT NULL
          );
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS feedback_visible_to_me")
    op.execute("DROP TRIGGER IF EXISTS trg_feedback_chunks_tsv ON feedback_chunks")
    op.execute("DROP FUNCTION IF EXISTS feedback_chunks_tsv_update")
    op.drop_table("access_log")
    op.drop_table("feedback_chunks")
    op.drop_table("sbi_instances")
    op.drop_table("feedback")
    op.drop_table("conversation_turns")
    op.drop_table("conversations")
    op.drop_table("topic_taxonomy")
    op.drop_table("unit_oversight")
    op.drop_table("org_subordinates")
    op.drop_table("org_units")
    op.drop_table("users")
    op.drop_table("orgs")
    op.execute("DROP TYPE IF EXISTS feedback_status")
    op.execute("DROP TYPE IF EXISTS sentiment")
    op.execute("DROP TYPE IF EXISTS subject_kind")
