"""Seed the demo org from CSV files in ops/seed/.

Idempotent: wipes the demo org and reloads. Run via:

    python -m app.seed

The pre-existing feedback records in feedback.csv come with sentiment and
topic_tags already labeled (skipping the post-submit Haiku extraction) so
the seed doesn't require Anthropic credentials. Embeddings are computed
via Voyage if VOYAGE_API_KEY is set, otherwise a zero vector is stored so
the rest of the schema is still valid.
"""

from __future__ import annotations

import asyncio
import csv
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, text

from app.closure import recompute
from app.db import engine, session_scope
from app.models import (
    Feedback,
    FeedbackChunk,
    FeedbackStatus,
    Org,
    OrgUnit,
    SBIInstance,
    Sentiment,
    SubjectKind,
    TopicTaxonomy,
    User,
)
from app.settings import get_settings

logger = logging.getLogger(__name__)


DEMO_ORG_NAME = "Demo Corp"


def _chunk_content(headline: str, sbis: list[tuple[str, str, str]]) -> str:
    """Compose the indexed chunk: headline + first 5 SBI bodies (design.md §4.2)."""
    parts = [headline]
    for s, b, i in sbis[:5]:
        parts.append(f"Situation: {s}\nBehavior: {b}\nImpact: {i}")
    return "\n\n".join(parts)


async def _embed(text_in: str) -> list[float]:
    """Voyage embedding; falls back to zeros so seed works without credentials."""
    settings = get_settings()
    if not settings.voyage_api_key:
        logger.warning("VOYAGE_API_KEY not set — using zero embedding")
        return [0.0] * 1024
    import voyageai  # type: ignore[import-untyped]

    client = voyageai.Client(api_key=settings.voyage_api_key)
    # Run sync SDK call in a thread.
    result = await asyncio.to_thread(
        client.embed, [text_in], model="voyage-3-large", input_type="document"
    )
    embedding = result.embeddings[0]
    assert len(embedding) == 1024, f"expected 1024-dim, got {len(embedding)}"
    return embedding


async def seed() -> None:
    settings = get_settings()
    seed_dir = settings.seed_dir
    if not seed_dir.exists():
        raise FileNotFoundError(f"seed dir not found: {seed_dir}")

    async with session_scope() as session:
        # Wipe any existing demo org.
        existing = (
            await session.execute(select(Org).where(Org.name == DEMO_ORG_NAME))
        ).scalar_one_or_none()
        if existing is not None:
            logger.info("wiping existing demo org")
            await session.execute(
                text("DELETE FROM feedback_chunks WHERE feedback_id IN "
                     "(SELECT id FROM feedback WHERE org_id = :oid)"),
                {"oid": existing.id},
            )
            await session.execute(
                text("DELETE FROM sbi_instances WHERE feedback_id IN "
                     "(SELECT id FROM feedback WHERE org_id = :oid)"),
                {"oid": existing.id},
            )
            await session.execute(text("DELETE FROM feedback WHERE org_id = :oid"), {"oid": existing.id})
            await session.execute(text("DELETE FROM conversation_turns WHERE conversation_id IN "
                                       "(SELECT id FROM conversations WHERE org_id = :oid)"),
                                  {"oid": existing.id})
            await session.execute(text("DELETE FROM conversations WHERE org_id = :oid"), {"oid": existing.id})
            await session.execute(text("DELETE FROM topic_taxonomy WHERE org_id = :oid"), {"oid": existing.id})
            await session.execute(text("DELETE FROM unit_oversight"))
            await session.execute(text("DELETE FROM org_subordinates"))
            await session.execute(text("DELETE FROM org_units WHERE org_id = :oid"), {"oid": existing.id})
            await session.execute(text("DELETE FROM users WHERE org_id = :oid"), {"oid": existing.id})
            await session.execute(text("DELETE FROM orgs WHERE id = :oid"), {"oid": existing.id})
            await session.commit()

        org = Org(name=DEMO_ORG_NAME)
        session.add(org)
        await session.flush()
        logger.info("created org %s (%s)", org.name, org.id)

        # Users — first pass without manager_id so FKs can resolve.
        user_id_by_handle: dict[str, uuid.UUID] = {}
        with (seed_dir / "users.csv").open() as f:
            user_rows = list(csv.DictReader(f))
        for row in user_rows:
            u = User(
                org_id=org.id,
                external_id=row["id"],
                name=row["name"],
                email=row["email"],
                title=row["title"] or None,
                active=True,
            )
            session.add(u)
            await session.flush()
            user_id_by_handle[row["id"]] = u.id
        # Second pass to set manager_id.
        for row in user_rows:
            if row["manager_id"]:
                u = (
                    await session.execute(
                        select(User).where(User.id == user_id_by_handle[row["id"]])
                    )
                ).scalar_one()
                u.manager_id = user_id_by_handle[row["manager_id"]]
        await session.commit()
        logger.info("seeded %d users", len(user_rows))

        # Org units — first pass without parent_unit_id; second pass to link.
        unit_id_by_handle: dict[str, uuid.UUID] = {}
        with (seed_dir / "org_units.csv").open() as f:
            unit_rows = list(csv.DictReader(f))
        for row in unit_rows:
            head = user_id_by_handle.get(row["head_user_id"]) if row["head_user_id"] else None
            unit = OrgUnit(org_id=org.id, name=row["name"], head_user_id=head)
            session.add(unit)
            await session.flush()
            unit_id_by_handle[row["id"]] = unit.id
        for row in unit_rows:
            if row["parent_unit_id"]:
                unit = (
                    await session.execute(
                        select(OrgUnit).where(OrgUnit.id == unit_id_by_handle[row["id"]])
                    )
                ).scalar_one()
                unit.parent_unit_id = unit_id_by_handle[row["parent_unit_id"]]
        await session.commit()
        logger.info("seeded %d org units", len(unit_rows))

        # Topic taxonomy.
        with (seed_dir / "topic_taxonomy.csv").open() as f:
            for row in csv.DictReader(f):
                session.add(
                    TopicTaxonomy(
                        org_id=org.id,
                        slug=row["slug"],
                        display_name=row["display_name"],
                        active=True,
                    )
                )
        await session.commit()

        # Closures.
        n_subs, n_over = await recompute(session)
        logger.info("recomputed closures: %d subordinate pairs, %d oversight pairs", n_subs, n_over)

        # Pre-existing feedback records (already labeled, treated as submitted).
        with (seed_dir / "feedback.csv").open() as f:
            feedback_rows = list(csv.DictReader(f))
        for row in feedback_rows:
            subject_kind = SubjectKind(row["subject_kind"])
            subject_user_id = (
                user_id_by_handle[row["subject_user_id"]] if row["subject_user_id"] else None
            )
            subject_unit_id = (
                unit_id_by_handle[row["subject_unit_id"]] if row["subject_unit_id"] else None
            )
            is_anon = row["is_anonymous"].lower() == "true"
            provider = None if is_anon else user_id_by_handle.get(row["provider_user_id"])
            fb = Feedback(
                org_id=org.id,
                provider_user_id=provider,
                is_anonymous=is_anon,
                subject_kind=subject_kind,
                subject_user_id=subject_user_id,
                subject_unit_id=subject_unit_id,
                headline=row["headline"],
                topic_tags=[s for s in row["topic_tags"].split(",") if s],
                sentiment=Sentiment(row["sentiment"]),
                sentiment_score=None,
                status=FeedbackStatus.submitted,
                submitted_at=datetime.now(UTC),
            )
            session.add(fb)
            await session.flush()
            # SBI: "situation||behavior||impact" — only one per seed record for brevity.
            sbi_parts = row["sbi"].split("||")
            if len(sbi_parts) == 3:
                s, b, i = (p.strip() for p in sbi_parts)
                session.add(
                    SBIInstance(
                        feedback_id=fb.id, idx=0, situation=s, behavior=b, impact=i
                    )
                )
                sbis = [(s, b, i)]
            else:
                sbis = []

            content = _chunk_content(fb.headline, sbis)
            embedding = await _embed(content)
            session.add(
                FeedbackChunk(feedback_id=fb.id, content=content, embedding=embedding)
            )
        await session.commit()
        logger.info("seeded %d feedback records", len(feedback_rows))


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s | %(message)s")
    await seed()
    await engine().dispose()


if __name__ == "__main__":
    asyncio.run(main())
