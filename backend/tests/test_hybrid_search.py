"""Integration tests for app.recipient.retrieval.hybrid_search.

The retrieval path fuses BM25 (Postgres tsv) and pgvector similarity via
RRF, *after* the feedback_visible_to_me ACL has already filtered the
candidate set. These tests pin the contract end-to-end against real
Postgres — including the ACL gate, the subject/topic/sentiment/date
filters, and the anonymity-aware shaping of provider_name.

The Voyage embedding call is stubbed (no API key in CI). All chunks get
the same dummy embedding so the vector ranker treats them equivalently;
BM25 and the SQL filters do the differentiating, which is what we want
to assert here.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.closure import recompute
from app.models import (
    Feedback,
    FeedbackChunk,
    FeedbackStatus,
    Org,
    SBIInstance,
    Sentiment,
    SubjectKind,
    User,
)
from app.recipient import retrieval

# Non-zero so pgvector cosine distance is defined.
_DUMMY_EMBEDDING = [0.0] * 1023 + [1.0]


@pytest.fixture(autouse=True)
def _stub_embed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the Voyage call with a fixed embedding for all tests in this module."""

    async def fake_embed(_text: str) -> list[float]:
        return _DUMMY_EMBEDDING

    monkeypatch.setattr(retrieval, "embed", fake_embed)


async def _set_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(text(f"SET LOCAL app.current_user_id = '{user_id}'"))


async def _seed_world(session: AsyncSession) -> dict[str, uuid.UUID]:
    """Tree: CEO ── MgrA ── IC1, IC2
                    └─ MgrB ── IC3
    Submit feedbacks about IC1/IC2/IC3 plus 1 draft about IC1.
    Returns ids the tests need.
    """
    # Uniquify emails — successive tests share the session-scoped Postgres.
    tag = uuid.uuid4().hex[:8]
    org = Org(name=f"HSTest-{tag}")
    session.add(org)
    await session.flush()
    ceo = User(org_id=org.id, name="Cee Eeo", email=f"ceo-{tag}@hs.test")
    session.add(ceo)
    await session.flush()
    mgr_a = User(org_id=org.id, name="Mgr A", email=f"ma-{tag}@hs.test", manager_id=ceo.id)
    mgr_b = User(org_id=org.id, name="Mgr B", email=f"mb-{tag}@hs.test", manager_id=ceo.id)
    session.add_all([mgr_a, mgr_b])
    await session.flush()
    ic1 = User(org_id=org.id, name="Ic One", email=f"ic1-{tag}@hs.test", manager_id=mgr_a.id)
    ic2 = User(org_id=org.id, name="Ic Two", email=f"ic2-{tag}@hs.test", manager_id=mgr_a.id)
    ic3 = User(org_id=org.id, name="Ic Three", email=f"ic3-{tag}@hs.test", manager_id=mgr_b.id)
    session.add_all([ic1, ic2, ic3])
    await session.flush()
    provider = User(
        org_id=org.id, name="Pat Provider", email=f"pp-{tag}@hs.test", manager_id=ceo.id
    )
    session.add(provider)
    await session.flush()
    await session.commit()
    await recompute(session)

    fb_ic1_jan = Feedback(
        org_id=org.id,
        provider_user_id=provider.id,
        subject_kind=SubjectKind.user,
        subject_user_id=ic1.id,
        headline="Strong code review habits",
        topic_tags=["quality"],
        sentiment=Sentiment.positive,
        status=FeedbackStatus.submitted,
        submitted_at=datetime(2026, 1, 10, tzinfo=UTC),
    )
    fb_ic1_feb_anon = Feedback(
        org_id=org.id,
        provider_user_id=provider.id,
        is_anonymous=True,
        subject_kind=SubjectKind.user,
        subject_user_id=ic1.id,
        headline="Missed standup repeatedly",
        topic_tags=["ownership"],
        sentiment=Sentiment.constructive,
        status=FeedbackStatus.submitted,
        submitted_at=datetime(2026, 2, 12, tzinfo=UTC),
    )
    fb_ic2_feb = Feedback(
        org_id=org.id,
        provider_user_id=provider.id,
        subject_kind=SubjectKind.user,
        subject_user_id=ic2.id,
        headline="Great mentoring of newer engineers",
        topic_tags=["growth"],
        sentiment=Sentiment.positive,
        status=FeedbackStatus.submitted,
        submitted_at=datetime(2026, 2, 20, tzinfo=UTC),
    )
    fb_ic2_mar = Feedback(
        org_id=org.id,
        provider_user_id=provider.id,
        subject_kind=SubjectKind.user,
        subject_user_id=ic2.id,
        headline="Specs need more detail before kickoff",
        topic_tags=["clarity"],
        sentiment=Sentiment.constructive,
        status=FeedbackStatus.submitted,
        submitted_at=datetime(2026, 3, 1, tzinfo=UTC),
    )
    fb_ic3_feb = Feedback(
        org_id=org.id,
        provider_user_id=provider.id,
        subject_kind=SubjectKind.user,
        subject_user_id=ic3.id,
        headline="Shipping reliably",
        topic_tags=["delivery"],
        sentiment=Sentiment.positive,
        status=FeedbackStatus.submitted,
        submitted_at=datetime(2026, 2, 15, tzinfo=UTC),
    )
    fb_draft = Feedback(
        org_id=org.id,
        provider_user_id=provider.id,
        subject_kind=SubjectKind.user,
        subject_user_id=ic1.id,
        headline="Draft about Ic One — should not surface",
        topic_tags=["draft"],
        sentiment=Sentiment.constructive,
        status=FeedbackStatus.draft,
        submitted_at=datetime(2026, 2, 1, tzinfo=UTC),
    )
    session.add_all([fb_ic1_jan, fb_ic1_feb_anon, fb_ic2_feb, fb_ic2_mar, fb_ic3_feb, fb_draft])
    await session.flush()

    # Chunks keyed by feedback_id; non-overlapping text so BM25 can pick winners.
    chunks = [
        (fb_ic1_jan.id, "code review pull request quality"),
        (fb_ic1_feb_anon.id, "missed standup ownership"),
        (fb_ic2_feb.id, "mentoring growth coaching juniors"),
        (fb_ic2_mar.id, "specification ambiguity kickoff"),
        (fb_ic3_feb.id, "shipping cadence reliability"),
        (fb_draft.id, "draft draft draft"),
    ]
    for fb_id, content in chunks:
        session.add(FeedbackChunk(feedback_id=fb_id, content=content, embedding=_DUMMY_EMBEDDING))

    # SBIs on one record (inserted out-of-order to verify the JSON build orders by idx).
    session.add_all(
        [
            SBIInstance(
                feedback_id=fb_ic2_mar.id,
                idx=1,
                situation="kickoff",
                behavior="spec was light",
                impact="rework",
            ),
            SBIInstance(
                feedback_id=fb_ic2_mar.id,
                idx=0,
                situation="planning",
                behavior="goals unclear",
                impact="confusion",
            ),
        ]
    )
    await session.commit()

    return {
        "ceo": ceo.id,
        "mgr_a": mgr_a.id,
        "mgr_b": mgr_b.id,
        "ic1": ic1.id,
        "ic2": ic2.id,
        "ic3": ic3.id,
        "provider": provider.id,
        "fb_ic1_jan": fb_ic1_jan.id,
        "fb_ic1_feb_anon": fb_ic1_feb_anon.id,
        "fb_ic2_feb": fb_ic2_feb.id,
        "fb_ic2_mar": fb_ic2_mar.id,
        "fb_ic3_feb": fb_ic3_feb.id,
        "fb_draft": fb_draft.id,
    }


async def _search_as(
    factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    **kwargs: Any,
) -> list[retrieval.RetrievedFeedback]:
    async with factory() as session:
        async with session.begin():
            await _set_user(session, user_id)
            return await retrieval.hybrid_search(session, **kwargs)


@pytest.mark.asyncio
async def test_acl_gates_results_to_what_caller_can_see(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        ids = await _seed_world(session)

    # Mgr A sees feedback about IC1 and IC2 (their reports), but NOT IC3
    # (under Mgr B). Submitted only — the draft is hidden even from the manager.
    results = await _search_as(session_factory, ids["mgr_a"], query="code")
    surfaced = {r.id for r in results}
    assert ids["fb_ic3_feb"] not in surfaced
    assert ids["fb_draft"] not in surfaced
    assert surfaced.issubset(
        {ids["fb_ic1_jan"], ids["fb_ic1_feb_anon"], ids["fb_ic2_feb"], ids["fb_ic2_mar"]}
    )

    # Mgr B sees only IC3's feedback.
    results = await _search_as(session_factory, ids["mgr_b"], query="ship")
    assert {r.id for r in results} == {ids["fb_ic3_feb"]}


@pytest.mark.asyncio
async def test_subject_user_ids_filter(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        ids = await _seed_world(session)

    results = await _search_as(
        session_factory,
        ids["ceo"],
        query="feedback",
        subject_user_ids=[ids["ic2"]],
    )
    assert {r.id for r in results} == {ids["fb_ic2_feb"], ids["fb_ic2_mar"]}


@pytest.mark.asyncio
async def test_sentiment_filter(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        ids = await _seed_world(session)

    results = await _search_as(
        session_factory, ids["ceo"], query="feedback", sentiment="constructive"
    )
    surfaced = {r.id for r in results}
    assert surfaced == {ids["fb_ic1_feb_anon"], ids["fb_ic2_mar"]}
    assert all(r.sentiment == "constructive" for r in results)


@pytest.mark.asyncio
async def test_topic_tags_filter_uses_array_overlap(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """`topic_tags && :topics` — overlap on any tag is enough."""
    async with session_factory() as session:
        ids = await _seed_world(session)

    results = await _search_as(
        session_factory,
        ids["ceo"],
        query="feedback",
        topic_slugs=["growth", "delivery"],
    )
    assert {r.id for r in results} == {ids["fb_ic2_feb"], ids["fb_ic3_feb"]}


@pytest.mark.asyncio
async def test_date_range_filter(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        ids = await _seed_world(session)

    # February only — Jan and Mar fall outside.
    results = await _search_as(
        session_factory,
        ids["ceo"],
        query="feedback",
        date_from=datetime(2026, 2, 1, tzinfo=UTC),
        date_to=datetime(2026, 2, 28, 23, 59, 59, tzinfo=UTC),
    )
    submitted_ats = [r.submitted_at for r in results]
    assert all(dt is not None and dt.month == 2 and dt.year == 2026 for dt in submitted_ats)
    surfaced = {r.id for r in results}
    assert ids["fb_ic1_jan"] not in surfaced
    assert ids["fb_ic2_mar"] not in surfaced


@pytest.mark.asyncio
async def test_anonymous_feedback_hides_provider_name(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Anonymity is enforced *in the retrieval shaping*, not just the UI.
    Even an admin pulling raw retrieval rows must not see the provider's
    name for anonymous feedback."""
    async with session_factory() as session:
        ids = await _seed_world(session)

    results = await _search_as(session_factory, ids["ceo"], query="standup")
    by_id = {r.id: r for r in results}
    assert by_id[ids["fb_ic1_feb_anon"]].provider_name is None

    # And the non-anonymous record on the other hand IS named.
    named = await _search_as(session_factory, ids["ceo"], query="code")
    by_id = {r.id: r for r in named}
    assert by_id[ids["fb_ic1_jan"]].provider_name == "Pat Provider"


@pytest.mark.asyncio
async def test_sbis_returned_ordered_by_idx(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        ids = await _seed_world(session)

    results = await _search_as(
        session_factory,
        ids["ceo"],
        query="specification",
        subject_user_ids=[ids["ic2"]],
    )
    match = next(r for r in results if r.id == ids["fb_ic2_mar"])
    # Inserted out-of-order (idx 1 first, then idx 0); the retrieval JSON
    # build orders by idx.
    assert [s["idx"] for s in match.sbis] == [0, 1]
    assert match.sbis[0]["situation"] == "planning"
    assert match.sbis[1]["situation"] == "kickoff"


@pytest.mark.asyncio
async def test_subject_name_populated_for_user_feedback(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        ids = await _seed_world(session)

    results = await _search_as(
        session_factory,
        ids["ceo"],
        query="feedback",
        subject_user_ids=[ids["ic2"]],
    )
    assert results, "expected at least one result for IC2"
    for r in results:
        assert r.subject_kind == "user"
        assert r.subject_user_name == "Ic Two"
        assert r.subject_unit_name is None
