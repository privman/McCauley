"""Hybrid retrieval for recipient mode (design.md §4.2, §6).

Searches feedback_visible_to_me — meaning the closure-based ACL is
applied implicitly by Postgres before any ranking. The query is a
hybrid of:

- BM25 via `tsv` ts_rank
- Vector similarity via pgvector cosine distance

Merged with Reciprocal Rank Fusion (k=60). RRF is a robust default that
doesn't need score calibration between the two systems.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.submit import embed

logger = logging.getLogger(__name__)

RRF_K = 60


@dataclass
class RetrievedFeedback:
    id: uuid.UUID
    headline: str
    sentiment: str | None
    topic_tags: list[str]
    subject_kind: str
    subject_user_name: str | None
    subject_unit_name: str | None
    submitted_at: datetime | None
    is_anonymous: bool
    provider_name: str | None
    sbis: list[dict[str, Any]]  # {idx, situation, behavior, impact}, ordered by idx
    score: float


async def hybrid_search(
    session: AsyncSession,
    *,
    query: str,
    subject_user_ids: list[uuid.UUID] | None = None,
    subject_unit_ids: list[uuid.UUID] | None = None,
    sentiment: str | None = None,
    topic_slugs: list[str] | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 8,
) -> list[RetrievedFeedback]:
    """Hybrid retrieval over feedback_visible_to_me.

    Pre-conditions: the caller must have already issued
    SET LOCAL app.current_user_id = ... on this session, so the view
    returns the right ACL slice.
    """
    embedding = await embed(query)
    vec_literal = "[" + ",".join(f"{x:.6f}" for x in embedding) + "]"

    filter_clauses: list[str] = []
    params: dict[str, object] = {"q": query, "vec": vec_literal, "limit": limit * 3}
    if subject_user_ids:
        params["subj_users"] = subject_user_ids
        filter_clauses.append("f.subject_user_id = ANY(:subj_users)")
    if subject_unit_ids:
        params["subj_units"] = subject_unit_ids
        filter_clauses.append("f.subject_unit_id = ANY(:subj_units)")
    if sentiment:
        params["sentiment"] = sentiment
        filter_clauses.append("f.sentiment = :sentiment")
    if topic_slugs:
        params["topics"] = topic_slugs
        filter_clauses.append("f.topic_tags && :topics")
    if date_from is not None:
        params["date_from"] = date_from
        filter_clauses.append("f.submitted_at >= :date_from")
    if date_to is not None:
        params["date_to"] = date_to
        filter_clauses.append("f.submitted_at <= :date_to")
    where_extra = " AND " + " AND ".join(filter_clauses) if filter_clauses else ""

    # Two ranked candidate sets, fused by RRF.
    sql = f"""
        WITH visible AS (
            SELECT f.id, f.headline, f.sentiment::text AS sentiment, f.topic_tags,
                   f.subject_kind::text AS subject_kind, f.subject_user_id,
                   f.subject_unit_id, f.submitted_at, f.is_anonymous,
                   f.provider_user_id,
                   c.content, c.embedding, c.tsv
            FROM feedback_visible_to_me f
            JOIN feedback_chunks c ON c.feedback_id = f.id
            WHERE TRUE {where_extra}
        ),
        bm25 AS (
            SELECT id, ROW_NUMBER() OVER (
                ORDER BY ts_rank(tsv, plainto_tsquery('english', :q)) DESC
            ) AS rk
            FROM visible
            WHERE tsv @@ plainto_tsquery('english', :q)
            LIMIT :limit
        ),
        vec AS (
            SELECT id, ROW_NUMBER() OVER (
                ORDER BY embedding <=> CAST(:vec AS vector)
            ) AS rk
            FROM visible
            LIMIT :limit
        ),
        fused AS (
            SELECT id, SUM(score) AS s FROM (
                SELECT id, 1.0/({RRF_K} + rk) AS score FROM bm25
                UNION ALL
                SELECT id, 1.0/({RRF_K} + rk) AS score FROM vec
            ) t
            GROUP BY id
        )
        SELECT v.id, v.headline, v.sentiment, v.topic_tags, v.subject_kind,
               u_sub.name AS subject_user_name,
               ou_sub.name AS subject_unit_name,
               v.submitted_at, v.is_anonymous,
               u_prov.name AS provider_name,
               COALESCE((
                   SELECT jsonb_agg(
                       jsonb_build_object(
                           'idx', s.idx,
                           'situation', s.situation,
                           'behavior', s.behavior,
                           'impact', s.impact
                       ) ORDER BY s.idx
                   )
                   FROM sbi_instances s
                   WHERE s.feedback_id = v.id
               ), '[]'::jsonb) AS sbis,
               f.s AS score
        FROM fused f
        JOIN visible v ON v.id = f.id
        LEFT JOIN users u_sub ON u_sub.id = v.subject_user_id
        LEFT JOIN org_units ou_sub ON ou_sub.id = v.subject_unit_id
        LEFT JOIN users u_prov ON u_prov.id = v.provider_user_id
        ORDER BY f.s DESC
        LIMIT :limit_final
    """
    params["limit_final"] = limit

    rows = (await session.execute(text(sql), params)).mappings().all()
    out: list[RetrievedFeedback] = []
    for r in rows:
        out.append(
            RetrievedFeedback(
                id=r["id"],
                headline=r["headline"],
                sentiment=r["sentiment"],
                topic_tags=list(r["topic_tags"] or []),
                subject_kind=r["subject_kind"],
                subject_user_name=r["subject_user_name"],
                subject_unit_name=r["subject_unit_name"],
                submitted_at=r["submitted_at"],
                is_anonymous=r["is_anonymous"],
                provider_name=None if r["is_anonymous"] else r["provider_name"],
                sbis=list(r["sbis"] or []),
                score=float(r["score"]),
            )
        )
    return out
