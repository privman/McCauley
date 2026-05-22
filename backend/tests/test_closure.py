"""Unit tests for the org-graph closure computation (app.closure).

These exercise the load-bearing correctness check that the per-subject ACL
(design.md §4.3) relies on. They use pure-Python inputs and never touch
Postgres, so they're fast and deterministic.
"""

from __future__ import annotations

import uuid

import pytest

from app.closure import (
    _UnitNode,
    _UserNode,
    compute_org_subordinates,
    compute_unit_oversight,
)


def _uid() -> uuid.UUID:
    return uuid.uuid4()


def test_org_subordinates_self_pair_only_for_isolated_user() -> None:
    a = _UserNode(id=_uid(), manager_id=None)
    pairs = compute_org_subordinates([a])
    assert pairs == {(a.id, a.id)}


def test_org_subordinates_simple_chain() -> None:
    ceo = _UserNode(id=_uid(), manager_id=None)
    vp = _UserNode(id=_uid(), manager_id=ceo.id)
    ic = _UserNode(id=_uid(), manager_id=vp.id)

    pairs = compute_org_subordinates([ceo, vp, ic])

    # IC is descendant of: ic, vp, ceo. VP: vp, ceo. CEO: ceo.
    assert (ic.id, ic.id) in pairs
    assert (vp.id, ic.id) in pairs
    assert (ceo.id, ic.id) in pairs
    assert (vp.id, vp.id) in pairs
    assert (ceo.id, vp.id) in pairs
    assert (ceo.id, ceo.id) in pairs
    assert len(pairs) == 6
    # IC is NOT an ancestor of anyone but themselves.
    assert (ic.id, vp.id) not in pairs
    assert (ic.id, ceo.id) not in pairs


def test_org_subordinates_branching_tree() -> None:
    ceo = _UserNode(id=_uid(), manager_id=None)
    vp_a = _UserNode(id=_uid(), manager_id=ceo.id)
    vp_b = _UserNode(id=_uid(), manager_id=ceo.id)
    ic_a = _UserNode(id=_uid(), manager_id=vp_a.id)
    ic_b = _UserNode(id=_uid(), manager_id=vp_b.id)

    pairs = compute_org_subordinates([ceo, vp_a, vp_b, ic_a, ic_b])

    # ic_a only visible up through vp_a, not vp_b
    assert (vp_a.id, ic_a.id) in pairs
    assert (vp_b.id, ic_a.id) not in pairs
    # ic_b only visible up through vp_b
    assert (vp_b.id, ic_b.id) in pairs
    assert (vp_a.id, ic_b.id) not in pairs
    # CEO sees both ICs
    assert (ceo.id, ic_a.id) in pairs
    assert (ceo.id, ic_b.id) in pairs


def test_org_subordinates_rejects_cycle() -> None:
    a_id, b_id = _uid(), _uid()
    a = _UserNode(id=a_id, manager_id=b_id)
    b = _UserNode(id=b_id, manager_id=a_id)
    with pytest.raises(ValueError, match="cycle"):
        compute_org_subordinates([a, b])


def test_unit_oversight_self_only_for_root() -> None:
    head = _uid()
    root = _UnitNode(id=_uid(), parent_id=None, head_user_id=head)
    pairs = compute_unit_oversight([root])
    assert pairs == {(head, root.id)}


def test_unit_oversight_propagates_up() -> None:
    ceo = _uid()
    vp = _uid()
    tl = _uid()
    org = _UnitNode(id=_uid(), parent_id=None, head_user_id=ceo)
    dept = _UnitNode(id=_uid(), parent_id=org.id, head_user_id=vp)
    team = _UnitNode(id=_uid(), parent_id=dept.id, head_user_id=tl)

    pairs = compute_unit_oversight([org, dept, team])

    # Team head sees team; VP sees dept and team (via parent); CEO sees all three.
    assert (tl, team.id) in pairs
    assert (vp, team.id) in pairs
    assert (ceo, team.id) in pairs
    assert (vp, dept.id) in pairs
    assert (ceo, dept.id) in pairs
    assert (ceo, org.id) in pairs
    # Team lead does NOT see the parent dept/org.
    assert (tl, dept.id) not in pairs
    assert (tl, org.id) not in pairs


def test_unit_oversight_handles_headless_unit() -> None:
    """A unit with no head still propagates oversight from ancestors."""
    ceo = _uid()
    org = _UnitNode(id=_uid(), parent_id=None, head_user_id=ceo)
    orphan = _UnitNode(id=_uid(), parent_id=org.id, head_user_id=None)

    pairs = compute_unit_oversight([org, orphan])

    # No head on orphan, but ceo (head of parent) oversees it.
    assert (ceo, orphan.id) in pairs
    # And ceo still sees the root.
    assert (ceo, org.id) in pairs


def test_unit_oversight_rejects_cycle() -> None:
    a_id, b_id = _uid(), _uid()
    a = _UnitNode(id=a_id, parent_id=b_id, head_user_id=None)
    b = _UnitNode(id=b_id, parent_id=a_id, head_user_id=None)
    with pytest.raises(ValueError, match="cycle"):
        compute_unit_oversight([a, b])
